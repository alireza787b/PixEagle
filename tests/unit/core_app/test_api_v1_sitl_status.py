import json
from pathlib import Path

from classes import api_v1_sitl as sitl
from tools.run_sitl_validation_suite import REQUIRED_PHASE2_SCENARIOS


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _copy_phase2_plan(tmp_path):
    source = PROJECT_ROOT / "tools" / "sitl_plans" / "phase2_follower_validation.json"
    target = tmp_path / "phase2_follower_validation.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def _write_manifest(run_dir, payload):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_sitl_validation_status_summarizes_plan_and_latest_manifest(
    monkeypatch,
    tmp_path,
):
    plan_path = _copy_phase2_plan(tmp_path)
    artifact_root = tmp_path / "reports" / "sitl"
    missing_artifacts = [f"missing/{index}.json" for index in range(14)]
    monkeypatch.setattr(sitl, "DEFAULT_SITL_PLAN_PATH", plan_path)
    monkeypatch.setattr(sitl, "DEFAULT_SITL_ARTIFACT_ROOT", artifact_root)
    monkeypatch.delenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", raising=False)

    _write_manifest(
        artifact_root / "older-run",
        {
            "run_id": "older-run",
            "updated_at": "2026-07-06T00:00:00+00:00",
            "plan": {"name": "phase2_follower_validation"},
            "result": "pass",
        },
    )
    _write_manifest(
        artifact_root / "new-run",
        {
            "run_id": "new-run",
            "mode": "execute",
            "result": "incomplete",
            "result_reason": "One or more required artifacts are missing.",
            "started_at": "2026-07-07T01:00:00+00:00",
            "finished_at": "2026-07-07T01:05:00+00:00",
            "updated_at": "2026-07-07T01:05:01+00:00",
            "plan": {"name": "phase2_follower_validation"},
            "scenario_execution": {
                "enabled": False,
                "control_actions_allowed": False,
            },
            "missing_or_placeholder_artifacts": missing_artifacts,
            "semantic_failures": ["mavlink_anywhere_required_outputs"],
            "artifact_content_failures": [],
        },
    )

    payload = sitl.get_sitl_validation_status_snapshot()

    assert payload["source"] == "pixeagle_sitl_validation_status"
    assert payload["profile"] == "official_px4_sih"
    assert payload["injections_enabled"] is False
    assert payload["raw_injection_controls_exposed"] is False
    assert payload["plan"]["name"] == "phase2_follower_validation"
    assert payload["plan"]["level"] == "L2"
    assert payload["plan"]["scenario_count"] == 9
    assert payload["plan"]["required_phase2_scenarios_missing"] == []
    assert payload["plan"]["px4_model"] == "sihsim_quadx"
    assert payload["commands"][0]["command"] == "make sitl-sih-dry-run"
    assert payload["commands"][0]["starts_processes"] is False
    assert payload["commands"][2]["command"] == "make sitl-sih-execute-px4"
    assert payload["commands"][2]["starts_processes"] is True
    assert payload["latest_run"]["available"] is True
    assert payload["latest_run"]["run_id"] == "new-run"
    assert payload["latest_run"]["result"] == "incomplete"
    assert payload["latest_run"]["artifact_dir"] == "new-run"
    assert payload["latest_run"]["missing_or_placeholder_count"] == 14
    assert len(payload["latest_run"]["missing_or_placeholder_artifacts"]) == 12
    assert payload["latest_run"]["missing_or_placeholder_truncated"] is True
    assert payload["latest_run"]["semantic_failures"] == [
        "mavlink_anywhere_required_outputs"
    ]
    assert str(tmp_path) not in json.dumps(payload)
    assert "not a runtime control surface" in payload["claim_boundary"]


def test_sitl_validation_status_reports_no_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(sitl, "DEFAULT_SITL_PLAN_PATH", _copy_phase2_plan(tmp_path))
    monkeypatch.setattr(
        sitl,
        "DEFAULT_SITL_ARTIFACT_ROOT",
        tmp_path / "reports" / "sitl",
    )

    payload = sitl.get_sitl_validation_status_snapshot()

    assert payload["latest_run"]["available"] is False
    assert payload["latest_run"]["run_id"] is None
    assert payload["commands"][1]["mode"] == "probe_only"


def test_sitl_validation_status_uses_harness_required_phase2_scenarios(
    monkeypatch,
    tmp_path,
):
    plan_path = _copy_phase2_plan(tmp_path)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["scenarios"] = [
        scenario
        for scenario in plan["scenarios"]
        if scenario.get("id") != "operator_abort"
    ]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(sitl, "DEFAULT_SITL_PLAN_PATH", plan_path)
    monkeypatch.setattr(
        sitl,
        "DEFAULT_SITL_ARTIFACT_ROOT",
        tmp_path / "reports" / "sitl",
    )

    payload = sitl.get_sitl_validation_status_snapshot()

    assert sitl.REQUIRED_PHASE2_SCENARIOS == REQUIRED_PHASE2_SCENARIOS
    assert "operator_abort" in payload["plan"]["required_phase2_scenarios_missing"]
    assert "operator_abort" not in payload["plan"]["required_phase2_scenarios_present"]


def test_sitl_validation_status_sanitizes_manifest_text_fields(
    monkeypatch,
    tmp_path,
):
    plan_path = _copy_phase2_plan(tmp_path)
    artifact_root = tmp_path / "reports" / "sitl"
    monkeypatch.setattr(sitl, "DEFAULT_SITL_PLAN_PATH", plan_path)
    monkeypatch.setattr(sitl, "DEFAULT_SITL_ARTIFACT_ROOT", artifact_root)

    _write_manifest(
        artifact_root / "path-leak-run",
        {
            "run_id": "path-leak-run",
            "updated_at": "2026-07-07T01:05:01+00:00",
            "plan": {"name": "phase2_follower_validation"},
            "result": "failed",
            "result_reason": (
                f"RuntimeError in {sitl.PROJECT_ROOT / 'reports/sitl/run/log.txt'} "
                "and /tmp/external-secret-path"
            ),
            "semantic_failures": [
                f"bad config at {sitl.PROJECT_ROOT / 'configs/config.yaml'}",
                "external /var/tmp/sitl/raw.txt",
            ],
            "artifact_content_failures": [
                f"missing {tmp_path / 'artifact.json'}",
            ],
        },
    )

    payload = sitl.get_sitl_validation_status_snapshot()
    serialized = json.dumps(payload)

    assert str(sitl.PROJECT_ROOT) not in serialized
    assert str(tmp_path) not in serialized
    assert "/tmp/external-secret-path" not in serialized
    assert "/var/tmp/sitl/raw.txt" not in serialized
    assert "reports/sitl/run/log.txt" in payload["latest_run"]["result_reason"]
    assert "<absolute-path>" in serialized
