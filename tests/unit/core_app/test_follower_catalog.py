"""Profile eligibility uses declared measurement meaning, not convenient fields."""

from dataclasses import replace
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from classes.follower_catalog import evaluate_aircraft, evaluate_input, get_follower_catalog, get_follower_profile
from classes.followers.base_follower import BaseFollower
from classes.schema_manager import SchemaManager
from classes.tracker_output import TrackerDataType


pytestmark = pytest.mark.unit


@pytest.fixture
def manager():
    return SchemaManager()


def test_all_registered_implementations_have_explicit_operator_and_command_contracts():
    from classes.follower_types import FollowerType

    catalog = {item.mode: item for item in get_follower_catalog()}
    assert set(catalog) == {item.value for item in FollowerType}
    assert {item.mode for item in catalog.values() if item.visibility == "basic"} == {
        "mc_velocity_position", "mc_velocity_chase",
    }
    assert all(item.description and item.implementation_available for item in catalog.values())
    assert all(item.required_fields for item in catalog.values() if item.control_type != "fixed_wing_external")
    assert catalog["gm_velocity_vector"].phase_command_contracts == {
        "multicopter": "velocity_body_offboard", "fixed_wing": "fixed_wing_external",
        "vtol_transition": "vtol_transition_external",
    }
    assert catalog["fw_attitude_rate"].phase_command_contracts == {"fixed_wing": "attitude_rate"}
    assert catalog["fw_attitude_rate"].live_eligibility.reason_code == "profile_not_live_qualified"
    assert catalog["gm_velocity_vector"].live_qualified_phases == ("multicopter", "fixed_wing")
    assert catalog["fw_attitude_rate"].live_qualified_phases == ()
    native = catalog["fw_navigation_chase"]
    assert native.phase_command_contracts == {"fixed_wing": "fixed_wing_external"}
    assert native.required_fields == () and native.live_qualified_phases == ()
    assert native.live_eligibility.reason_code == "profile_not_live_qualified"
    assert all("multicopter" in item.live_qualified_phases for item in catalog.values()
               if item.airframe_phase == "multicopter")


def test_native_command_contract_cannot_grant_live_qualification():
    profile = replace(
        get_follower_profile("fw_attitude_rate"),
        native_phase_contracts=(("fixed_wing", "fixed_wing_external"),),
    )
    assert profile.phase_command_contracts == {"fixed_wing": "fixed_wing_external"}
    assert not profile.live_eligibility.eligible
    assert evaluate_aircraft(profile, "fixed_wing").reason_code == "profile_not_live_qualified"


@pytest.mark.parametrize("mode,transport,eligible", [
    ("mc_velocity_chase", "mavsdk", True),
    ("gm_velocity_vector", "mavsdk", True),
    ("fw_attitude_rate", "mavsdk", True),
    ("fw_navigation_chase", "px4_native", False),
])
def test_preview_admission_uses_the_nominal_transport_not_live_qualification(mode, transport, eligible):
    profile = get_follower_profile(mode)
    assert profile.command_transport == transport
    assert profile.preview_eligibility.eligible is eligible
    assert profile.preview_eligibility.reason_code == (None if eligible else "command_preview_transport_unsupported")


def test_preview_transport_admission_is_generic_and_never_grants_live_authority():
    profile = replace(get_follower_profile("fw_navigation_chase"), mode="future_native_follower",
                      live_qualified_phases=("fixed_wing",))
    assert profile.live_eligibility.eligible
    assert profile.preview_eligibility.reason_code == "command_preview_transport_unsupported"
    profile = replace(profile, command_transport="mavsdk", live_qualified_phases=())
    assert profile.preview_eligibility.eligible
    assert not profile.live_eligibility.eligible
    assert replace(profile, implementation_available=False).preview_eligibility.reason_code == "follower_implementation_unavailable"
    assert replace(profile, command_transport="future_transport").preview_eligibility.reason_code == "command_preview_transport_unsupported"


def test_qualification_for_one_phase_does_not_admit_another_declared_phase():
    profile = replace(get_follower_profile("gm_velocity_vector"), live_qualified_phases=("multicopter",))
    assert profile.live_eligibility.eligible
    assert evaluate_aircraft(profile, "multicopter").eligible
    assert evaluate_aircraft(profile, "fixed_wing").reason_code == "profile_not_live_qualified"


def test_explicit_transition_qualification_cannot_bypass_the_vtol_release_gate():
    profile = replace(get_follower_profile("gm_velocity_vector"), live_qualified_phases=("vtol_transition",))
    assert profile.live_eligibility.eligible
    assert evaluate_aircraft(profile, "vtol", observed_phase="vtol_transition").reason_code == "following_transition_unavailable"
    assert evaluate_aircraft(profile, "vtol", observed_phase="fixed_wing").reason_code == "vtol_transition_release_unqualified"


@pytest.mark.parametrize("value", [None, "fixed_wing", ["unknown"], ["multicopter", "multicopter"], [True], [{}]])
def test_unvalidated_catalog_inputs_cannot_infer_qualification(value):
    from classes.follower import FollowerFactory
    from classes.follower_catalog import FollowerProfile

    info = {**FollowerFactory.get_follower_info("mc_velocity_chase"), "live_qualified_phases": value}
    with pytest.raises(ValueError, match="live_qualified_phases"):
        FollowerProfile.from_info("mc_velocity_chase", info)


@pytest.mark.parametrize("schema,tracker,eligible", [
    ("POSITION_2D", "CSRTTracker", True),
    ("POSITION_3D", None, True),
    ("VELOCITY_AWARE", None, True),
    ("MULTI_TARGET", None, False),
    ("MULTI_TARGET", "SmartTracker", True),
    ("BBOX_CONFIDENCE", None, False),
    ("ANGULAR", None, False),
    ("GIMBAL_ANGLES", "GimbalTracker", False),
    ("EXTERNAL", None, False),
    ("UNKNOWN", None, False),
    ("POSITION_2D", "UnknownTracker", False),
    ("POSITION_2D", "SmartTracker", False),
])
def test_static_selection_requires_guaranteed_fields_and_representation(manager, schema, tracker, eligible):
    result = evaluate_input(get_follower_profile("mc_velocity_chase"), manager, schema, tracker_name=tracker)
    assert result.eligible is eligible


@pytest.mark.parametrize("schema,fields,eligible", [
    ("POSITION_2D", {"position_2d": (.1, .2)}, True),
    ("POSITION_2D", {"position_2d": None}, False),
    ("MULTI_TARGET", {"position_2d": (.1, .2)}, True),
    ("MULTI_TARGET", {"position_2d": None}, False),
    ("BBOX_CONFIDENCE", {"bbox": (1, 2, 3, 4)}, False),
    ("BBOX_CONFIDENCE", {"position_2d": (.1, .2)}, True),
    ("GIMBAL_ANGLES", {"angular": (5., 90., 1.), "position_2d": (.1, .2)}, False),
    ("EXTERNAL", {"position_2d": (.1, .2)}, False),
])
def test_runtime_sample_needs_actual_fields_and_cannot_change_representation(manager, schema, fields, eligible):
    result = evaluate_input(get_follower_profile("mc_velocity_position"), manager, schema, sample_fields=fields)
    assert result.eligible is eligible


@pytest.mark.parametrize("mode", ["gm_velocity_chase", "gm_velocity_vector"])
def test_provider_angle_profiles_do_not_accept_unrelated_angular_pairs(manager, mode):
    profile = get_follower_profile(mode)
    assert evaluate_input(profile, manager, "GIMBAL_ANGLES", sample_fields={"angular": (0, 90, 0)}).eligible
    assert not evaluate_input(profile, manager, "ANGULAR", sample_fields={"angular": (0, 90)}).eligible
    assert not evaluate_input(profile, manager, "POSITION_2D", sample_fields={"position_2d": (0, 0)}).eligible


@pytest.mark.parametrize("schema,position,eligible", [
    (TrackerDataType.POSITION_2D, (.1, .2), True),
    (TrackerDataType.POSITION_2D, None, False),
    (TrackerDataType.MULTI_TARGET, (.1, .2), True),
    (TrackerDataType.GIMBAL_ANGLES, (.1, .2), False),
    (TrackerDataType.EXTERNAL, (.1, .2), False),
])
def test_base_follower_uses_same_evaluator_for_real_samples(schema, position, eligible):
    stub = SimpleNamespace(profile_name="mc_velocity_position", _rate_limiter=Mock(), _error_aggregator=Mock())
    sample = SimpleNamespace(data_type=schema, tracking_active=True, position_2d=position, angular=(0, 90, 0))
    assert BaseFollower.validate_tracker_compatibility(stub, sample) is eligible


def test_static_promise_never_substitutes_for_a_missing_runtime_sample(manager):
    profile = get_follower_profile("mc_velocity_chase")
    assert evaluate_input(profile, manager, "MULTI_TARGET", tracker_name="SmartTracker").eligible
    assert not evaluate_input(profile, manager, "MULTI_TARGET", sample_fields={"position_2d": None}).eligible


@pytest.mark.parametrize("value", [(float("nan"), 0.), (0., float("inf")), (True, 0.), ("1", 0.), (1.,), "0,0"])
def test_present_but_malformed_image_measurements_are_not_eligible(manager, value):
    result = evaluate_input(get_follower_profile("mc_velocity_position"), manager, "POSITION_2D",
                            sample_fields={"position_2d": value})
    assert result.reason_code == "tracker_required_fields_invalid"


def test_missing_implementation_and_unknown_semantics_fail_closed(manager):
    profile = replace(get_follower_profile("mc_velocity_chase"), implementation_available=False)
    assert evaluate_input(profile, manager, "POSITION_2D").reason_code == "follower_implementation_unavailable"
    assert profile.live_eligibility.reason_code == "follower_implementation_unavailable"
    manager.schemas["POSITION_2D"].pop("representation")
    assert evaluate_input(get_follower_profile("mc_velocity_chase"), manager, "POSITION_2D").reason_code == "tracker_output_unknown"


def test_declared_but_unimplemented_profile_remains_visible_and_unavailable(manager, monkeypatch):
    from classes.setpoint_handler import SetpointHandler

    get_follower_catalog()
    schema = deepcopy(SetpointHandler._schema_cache)
    schema["follower_profiles"]["future_profile"] = deepcopy(schema["follower_profiles"]["mc_velocity_position"])
    monkeypatch.setattr(SetpointHandler, "_schema_cache", schema)
    profile = next(item for item in get_follower_catalog() if item.mode == "future_profile")
    assert not profile.implementation_available
    assert not profile.live_eligibility.eligible
    assert not evaluate_input(profile, manager, "POSITION_2D").eligible


@pytest.mark.parametrize("mode,kind,phase,reason", [
    ("mc_velocity_chase", "multicopter", None, None),
    ("mc_velocity_chase", "fixed_wing", None, "follower_aircraft_incompatible"),
    ("gm_velocity_vector", "fixed_wing", "fixed_wing", None),
    ("fw_attitude_rate", "fixed_wing", None, "profile_not_live_qualified"),
    ("gm_velocity_vector", "unknown", None, "aircraft_kind_unavailable"),
    ("gm_velocity_vector", "vtol", "vtol_transition", "following_transition_unavailable"),
    ("gm_velocity_vector", "vtol", "multicopter", "vtol_transition_release_unqualified"),
    ("gm_velocity_vector", "fixed_wing", "multicopter", "aircraft_phase_mismatch"),
])
def test_aircraft_start_gate_does_not_grant_unqualified_vtol_or_rate_authority(mode, kind, phase, reason):
    result = evaluate_aircraft(get_follower_profile(mode), kind, observed_phase=phase)
    assert result.reason_code == reason
    assert result.eligible is (reason is None)


def test_invalid_tracker_promise_is_not_loaded(tmp_path, manager):
    path = tmp_path / "schema.yaml"
    path.write_text(yaml.safe_dump({
        "tracker_data_types": manager.schemas,
        "tracker_types": {"Broken": {"data_type": "POSITION_2D", "following_required_fields": ["invented_field"]}},
    }))
    invalid = SchemaManager(str(path))
    assert invalid.get_schema_summary()["loaded"] is False
    assert invalid.get_schema("POSITION_2D") is None
