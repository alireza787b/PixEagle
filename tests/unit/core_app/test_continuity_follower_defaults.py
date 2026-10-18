from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from classes.target_continuity import ContinuityMode, ContinuityPolicy
from tests.unit.core_app.test_target_continuity import (
    _context, _evidence, _intent, _policy, _supervisor,
)
from classes.target_continuity import TargetEvidenceState


def test_fresh_defaults_scope_recovery_to_gimbal_followers():
    path = Path(__file__).resolve().parents[3] / "configs/config_default.yaml"
    config = yaml.safe_load(path.read_text())
    for name in ("gm_velocity_chase", "gm_velocity_vector"):
        policy = ContinuityPolicy.resolve(config["TargetContinuity"], name)
        assert policy.mode is ContinuityMode.BOUNDED_DECAY
        assert policy.max_coast_time_s == policy.max_retarget_time_s == 8.0
        assert policy.max_coast_distance_m == 4.0
        assert policy.authority_restore_time_s == 0.5
    ordinary = ContinuityPolicy.resolve(config["TargetContinuity"], "mc_velocity_chase")
    assert ordinary.mode is ContinuityMode.IMMEDIATE_HANDOFF
    assert ordinary.max_retarget_time_s == 3.0


def test_legacy_policy_is_not_implicitly_upgraded():
    raw = {"MODE": "immediate_handoff", "MAX_RETARGET_TIME_S": 6.0}
    policy = ContinuityPolicy.resolve(raw, "gm_velocity_vector")
    assert policy.mode is ContinuityMode.IMMEDIATE_HANDOFF
    assert policy.max_retarget_time_s == 6.0
    assert "FollowerOverrides" not in raw


@pytest.mark.parametrize("overrides", [
    None, {"UNKNOWN": {}}, {"GM_VELOCITY_CHASE": None},
    {"GM_VELOCITY_CHASE": {"MODE": "unknown"}},
    {"GM_VELOCITY_CHASE": {"MAX_COAST_TIME_S": float("nan")}},
    {"GM_VELOCITY_CHASE": {"FollowerOverrides": {}}},
])
def test_all_override_policies_are_validated_before_publication(overrides):
    with pytest.raises(ValueError):
        ContinuityPolicy.resolve({"FollowerOverrides": overrides}, "mc_velocity_chase")


def test_sparse_overrides_inherit_saved_policy_and_do_not_mutate_it():
    raw = {"MAX_COAST_DISTANCE_M": 7.0, "FollowerOverrides": {
        "GM_VELOCITY_CHASE": {"MODE": "bounded_decay", "MAX_COAST_TIME_S": 8.0},
    }}
    policy = ContinuityPolicy.resolve(raw, "gm_velocity_chase")
    assert policy.max_coast_distance_m == 7.0
    raw["FollowerOverrides"]["GM_VELOCITY_CHASE"]["MAX_COAST_TIME_S"] = 9.0
    assert policy.max_coast_time_s == 8.0


def test_recovery_distance_uses_actual_submitted_command():
    supervisor = _supervisor(_policy("bounded_decay", MAX_COAST_DISTANCE_M=10.0))
    supervisor.evaluate(_evidence(TargetEvidenceState.CONFIRMED), _context(),
                        _intent(forward=4.0, right=0.0), now_monotonic_s=0.0)
    supervisor.record_authorized_intent(_intent(forward=0.4, right=0.0))
    lost = supervisor.evaluate(_evidence(TargetEvidenceState.ABSENT), _context(),
                               now_monotonic_s=0.1)
    assert lost.authorized_intent.fields["vel_body_fwd"] == pytest.approx(0.4)
    submitted = replace(lost.authorized_intent, fields={
        **lost.authorized_intent.fields, "vel_body_fwd": 0.2,
    })
    supervisor.record_authorized_intent(submitted)
    later = supervisor.evaluate(_evidence(TargetEvidenceState.ABSENT), _context(),
                                now_monotonic_s=0.6)
    assert later.coast_distance_m == pytest.approx(0.1)
    assert supervisor.get_status()["effective_command_fields"] == later.authorized_intent.fields


def test_submitted_command_cannot_invent_authority_or_change_profile():
    supervisor = _supervisor(_policy())
    with pytest.raises(ValueError, match="No current"):
        supervisor.record_authorized_intent(_intent())
    supervisor.evaluate(_evidence(TargetEvidenceState.CONFIRMED), _context(),
                        _intent(), now_monotonic_s=0.0)
    with pytest.raises(ValueError, match="does not match"):
        supervisor.record_authorized_intent(replace(_intent(), profile_name="gm_velocity_vector"))


def test_diagnostics_distinguish_missing_policy_from_explicit_migration():
    config = yaml.safe_load((Path(__file__).resolve().parents[3] / "configs/config_default.yaml").read_text())
    legacy = _supervisor(ContinuityPolicy.resolve(None, "gm_velocity_vector"))
    assert legacy.get_status()["configuration_origin"] == "compatibility_defaults"
    assert legacy.get_status()["effective_policy"]["max_coast_distance_m"] == 2.0
    migrated = _supervisor(ContinuityPolicy.resolve(config["TargetContinuity"], "gm_velocity_vector"))
    status = migrated.get_status()
    assert status["configuration_origin"] == "follower_override:GM_VELOCITY_VECTOR"
    assert status["effective_policy"]["max_coast_time_s"] == 8.0
    assert status["effective_policy"]["max_coast_distance_m"] == 4.0
    global_policy = ContinuityPolicy.resolve({"MODE": "immediate_handoff"}, "gm_velocity_vector")
    assert global_policy.configuration_origin == "configured_global"


def test_missing_continuity_is_explicit_config_sync_addition(tmp_path):
    import copy
    import shutil
    from classes.config_service import ConfigService
    from classes.config_sync import ConfigSyncOperation, build_defaults_sync_plan, build_defaults_sync_report

    source = Path(__file__).resolve().parents[3] / "configs"
    destination = tmp_path / "configs"
    destination.mkdir()
    for name in ("config_default.yaml", "config_schema.yaml", "config_retirements.yaml"):
        shutil.copyfile(source / name, destination / name)
    saved = yaml.safe_load((source / "config_default.yaml").read_text())
    del saved["TargetContinuity"]
    (destination / "config.yaml").write_text(yaml.safe_dump(saved))
    service = ConfigService(project_root=tmp_path)
    before = copy.deepcopy(service.get_config())
    report = build_defaults_sync_report(service)
    additions = [item["path"] for item in report["new_parameters"] if item["path"][0] == "TargetContinuity"]
    assert additions
    plan = build_defaults_sync_plan(service, [ConfigSyncOperation(op_type="ADD_NEW", path=path) for path in additions])
    assert plan["valid"], plan["errors"]
    assert service.get_config() == before
    migrated = copy.deepcopy(before)
    for operation in plan["operations"]:
        section, parameter = operation["path"]
        migrated.setdefault(section, {})[parameter] = operation["target_value"]
    assert {k: v for k, v in migrated.items() if k != "TargetContinuity"} == before
    for follower in ("gm_velocity_chase", "gm_velocity_vector"):
        policy = ContinuityPolicy.resolve(migrated["TargetContinuity"], follower)
        assert policy.mode is ContinuityMode.BOUNDED_DECAY
        assert policy.max_coast_time_s == policy.max_retarget_time_s == 8.0
        assert policy.max_coast_distance_m == 4.0
