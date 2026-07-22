"""Static contracts for tracker claims and retired follower-control settings."""

from pathlib import Path

import yaml

from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(relative_path: str):
    return yaml.safe_load(
        (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    )


def test_classic_tracker_catalog_requires_scenario_evidence():
    catalog = _load_yaml("configs/tracker_schemas.yaml")["tracker_types"]

    for tracker_name in ("CSRTTracker", "KCFKalmanTracker", "DlibTracker"):
        tracker = catalog[tracker_name]
        assert "occlusion_handling" not in tracker["capabilities"]
        assert tracker["performance"]["evidence_required"] is True
        assert "accuracy" not in tracker["performance"]
        assert "speed" not in tracker["performance"]
        assert tracker["ui_metadata"]["performance_category"] == "scenario_dependent"


def test_unimplemented_particle_filter_and_prediction_control_are_retired():
    defaults = _load_yaml("configs/config_default.yaml")
    schema = _load_yaml("configs/config_schema.yaml")
    retirements = _load_yaml("configs/config_retirements.yaml")["retirements"]
    retired_paths = {tuple(item["path"]) for item in retirements}
    active_legacy_edge_names = {
        "PF_CANNY_THRESHOLD1",
        "PF_CANNY_THRESHOLD2",
    }
    assert {
        name for name in defaults["Tracking"] if name.startswith("PF_")
    } == active_legacy_edge_names
    assert {
        name
        for name in schema["sections"]["Tracking"]["parameters"]
        if name.startswith("PF_")
    } == active_legacy_edge_names
    assert "USE_ESTIMATOR_FOR_FOLLOWING" not in defaults["Estimator"]
    assert (
        "USE_ESTIMATOR_FOR_FOLLOWING"
        not in schema["sections"]["Estimator"]["parameters"]
    )

    assert ("Estimator", "USE_ESTIMATOR_FOR_FOLLOWING") in retired_paths
    assert defaults["Tracking"]["PF_CANNY_THRESHOLD1"] == 50
    assert defaults["Tracking"]["PF_CANNY_THRESHOLD2"] == 150
    assert ("Tracking", "PF_CANNY_THRESHOLD1") not in retired_paths
    assert ("Tracking", "PF_CANNY_THRESHOLD2") not in retired_paths
    for old_name in (
        "PF_NUM_PARTICLES",
        "PF_INIT_POS_STD",
        "PF_INIT_VEL_STD",
        "PF_INIT_ACC_STD",
        "PF_POS_STD",
        "PF_VEL_STD",
        "PF_ACC_STD",
        "PF_APPEARANCE_LIKELIHOOD_SCALE",
        "PF_APPEARANCE_LEARNING_RATE",
        "PF_COLOR_WEIGHT",
        "PF_EDGE_WEIGHT",
        "PF_EFFECTIVE_PARTICLE_NUM_THRESHOLD",
        "PF_RANDOM_PARTICLE_RATIO",
    ):
        assert ("Tracking", old_name) in retired_paths


def test_distance_follower_catalog_does_not_claim_range_control():
    compatibility = _load_yaml("configs/tracker_schemas.yaml")["compatibility"]
    distance = compatibility["followers"]["MCVelocityDistanceFollower"]

    assert "preferred_schemas" not in distance


def test_chase_cadence_and_gimbal_forward_modes_match_runtime():
    defaults = _load_yaml("configs/config_default.yaml")
    schema = _load_yaml("configs/config_schema.yaml")
    retired_paths = {
        tuple(item["path"])
        for item in _load_yaml("configs/config_retirements.yaml")["retirements"]
    }

    mc_chase = defaults["MC_VELOCITY_CHASE"]
    mc_chase_schema = schema["sections"]["MC_VELOCITY_CHASE"]["parameters"]
    assert "RAMP_UPDATE_RATE" in mc_chase
    assert "PID_UPDATE_RATE" not in mc_chase
    assert "PID_UPDATE_RATE" not in mc_chase_schema
    assert ("MC_VELOCITY_CHASE", "PID_UPDATE_RATE") in retired_paths

    mode_options = {
        item["value"]
        for item in schema["sections"]["GM_VELOCITY_CHASE"]["parameters"][
            "FORWARD_VELOCITY_MODE"
        ]["options"]
    }
    assert mode_options == GMVelocityChaseFollower.SUPPORTED_FORWARD_VELOCITY_MODES


def test_active_docs_do_not_advertise_unimplemented_pn_mode():
    assert not (
        PROJECT_ROOT / "docs/developers/FORWARD_VELOCITY_RESEARCH_GUIDE.md"
    ).exists()
    pn_note = (
        PROJECT_ROOT / "docs/followers/03-gnc-concepts/proportional-navigation.md"
    ).read_text(encoding="utf-8")
    forward_modes = (
        PROJECT_ROOT / "docs/followers/03-gnc-concepts/gimbal-forward-speed.md"
    ).read_text(encoding="utf-8")

    assert "does **not** currently implement PN" in pn_note
    assert "`PROPORTIONAL_NAV` and hybrid modes are not implemented" in forward_modes
