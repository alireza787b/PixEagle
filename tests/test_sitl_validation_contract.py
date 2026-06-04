"""Static contract tests for the PX4/SITL validation harness."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = PROJECT_ROOT / "tools" / "run_sitl_validation_suite.py"
PLAN_DIR = PROJECT_ROOT / "tools" / "sitl_plans"
SIH_PROFILE_SCRIPT = PROJECT_ROOT / "scripts" / "sitl" / "run_px4_sih_profile.sh"
GAZEBO_PROFILE_SCRIPT = PROJECT_ROOT / "scripts" / "sitl" / "run_px4_gazebo_visual_profile.sh"
SIH_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "px4-sih-validation.yml"
GAZEBO_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "px4-gazebo-visual-validation.yml"
MAKEFILE = PROJECT_ROOT / "Makefile"


def load_harness_module():
    spec = importlib.util.spec_from_file_location("pixeagle_sitl_harness", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sitl_plans_validate_and_cover_phase2_required_scenarios():
    harness = load_harness_module()
    scenario_ids = set()

    for path in harness.plan_files():
        plan = harness.load_plan(path)
        assert plan["schema_version"] == 1
        scenario_ids.update(scenario["id"] for scenario in plan["scenarios"])

    assert harness.REQUIRED_PHASE2_SCENARIOS <= scenario_ids


def test_phase2_plan_declares_required_evidence_contract():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    evidence_contract = set(plan["evidence_contract"])
    assert harness.REQUIRED_EVIDENCE_ARTIFACTS == evidence_contract
    assert "px4/ulog_manifest.json" in evidence_contract
    assert "px4/tlog_manifest.json" in evidence_contract
    assert "px4/params.txt" in evidence_contract
    assert "px4/container_metadata.json" in evidence_contract
    assert "route_map/mavlink_anywhere_status.json" in evidence_contract
    assert "route_map/mavlink_anywhere_endpoints.json" in evidence_contract
    assert "scenarios/scenario_results.json" in evidence_contract


def test_gazebo_visual_plan_declares_official_image_video_contract_and_extra_evidence():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "gazebo_visual_validation.json")
    summary = harness.build_summary(plan, PLAN_DIR / "gazebo_visual_validation.json")

    px4 = plan["stack"]["px4"]
    video = plan["stack"]["video"]
    evidence_contract = set(plan["evidence_contract"])

    assert plan["level"] == "L4"
    assert px4["recommended_image"] == "px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01"
    assert px4["vehicle_model"] == "gz_x500_mono_cam"
    assert px4["environment"]["HEADLESS"] == "1"
    assert px4["require_container_metadata"] is True
    assert px4["require_image_repo_digest"] is True
    assert px4["expected_repo_digest"] == (
        "px4io/px4-sitl-gazebo@"
        "sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db"
    )
    assert px4["ports"]["gazebo_video_udp"] == 5600
    assert video["source"] == "gazebo_rtp_h264_udp"
    assert "video/generated_receiver_proof_manifest.json" in evidence_contract
    assert "video/gazebo_receiver_pipeline.txt" in evidence_contract
    assert "video/gazebo_frame_hashes.json" in evidence_contract
    assert "trace/tracker_command_trace.jsonl" in evidence_contract
    assert "trace/offboard_publish_trace.jsonl" in evidence_contract
    assert summary["required_phase2_applicable"] is False
    assert summary["required_phase2_scenarios_missing"] == []


def test_gazebo_visual_container_command_includes_headless_env_and_model_override():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "gazebo_visual_validation.json")

    container_name, command = harness.build_px4_container_command(
        plan,
        "run-id",
        image_override=None,
        model_override="gz_x500_gimbal",
        container_name_override=None,
    )

    assert container_name == "pixeagle-px4-sitl-run-id"
    assert "px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01" == command[-1]
    command_text = " ".join(command)
    assert "HEADLESS=1" in command_text
    assert "PX4_SIM_MODEL=gz_x500_gimbal" in command_text


def strict_h264_rtp_pipeline(port=5600):
    return (
        f'udpsrc uri=udp://0.0.0.0:{port} '
        'caps="application/x-rtp,media=video,encoding-name=H264,'
        'payload=96,clock-rate=90000" ! rtph264depay ! h264parse ! '
        'avdec_h264 ! videoconvert ! video/x-raw,format=BGR ! videoscale ! '
        'video/x-raw,width=320,height=240 ! appsink drop=true max-buffers=1 sync=false'
    )


def write_valid_gazebo_visual_evidence(run_dir):
    (run_dir / "video").mkdir(parents=True, exist_ok=True)
    (run_dir / "trace").mkdir(parents=True, exist_ok=True)
    (run_dir / "px4").mkdir(parents=True, exist_ok=True)

    image_id = "sha256:" + "1" * 64
    image_inspect = [
        {
            "Id": image_id,
            "RepoTags": ["px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01"],
            "RepoDigests": [
                "px4io/px4-sitl-gazebo@"
                "sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db"
            ],
        }
    ]
    container_inspect = [{"Id": "container-id", "Image": image_id, "Name": "/px4"}]
    (run_dir / "px4" / "container_metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "collected": True,
                "image": "px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01",
                "container_name": "operator-px4",
                "container_id": None,
                "image_inspect": {
                    "returncode": 0,
                    "stdout": json.dumps(image_inspect),
                    "stderr": "",
                },
                "container_inspect": {
                    "returncode": 0,
                    "stdout": json.dumps(container_inspect),
                    "stderr": "",
                },
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "video" / "generated_receiver_proof_manifest.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "mode": "execute",
                "fresh_ok": True,
                "stale_unusable_ok": True,
                "dimensions_ok": True,
                "fresh_frame_count": 8,
                "receiver_pipeline": strict_h264_rtp_pipeline(5636),
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "video" / "gazebo_receiver_pipeline.txt").write_text(
        strict_h264_rtp_pipeline(5600),
        encoding="utf-8",
    )
    (run_dir / "video" / "gazebo_frame_hashes.json").write_text(
        json.dumps(
            {
                "all": [
                    {"index": 0, "sha256": "a" * 64, "shape": [240, 320, 3]},
                    {"index": 1, "sha256": "b" * 64, "shape": [240, 320, 3]},
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace" / "tracker_command_trace.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_type": "tracker_command",
                "timestamp": 1.0,
                "frame_index": 0,
                "source": "unit_test",
                "tracker_output": {
                    "tracker_id": "synthetic",
                    "data_type": "POSITION_2D",
                    "timestamp": 1.0,
                    "tracking_active": True,
                    "has_output": True,
                    "usable_for_following": True,
                    "data_is_stale": False,
                    "freshness_reason": "measurement",
                    "bbox": [1, 2, 3, 4],
                    "position_2d": [0.1, -0.1],
                },
                "command_intent": {
                    "profile_name": "mc_velocity_position",
                    "control_type": "velocity_body",
                    "source": "follower",
                    "reason": "mc_velocity_position_normal_tracking",
                    "fields": {
                        "vel_body_down": 0.0,
                        "yawspeed_deg_s": 1.0,
                    },
                },
                "dispatch_accepted": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "trace" / "offboard_publish_trace.jsonl").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record_type": "offboard_publish",
                "timestamp": 1.1,
                "sequence": 0,
                "source": "unit_test",
                "command_intent": {
                    "profile_name": "mc_velocity_position",
                    "control_type": "velocity_body",
                    "source": "follower",
                    "reason": "mc_velocity_position_normal_tracking",
                    "fields": {
                        "vel_body_down": 0.0,
                        "yawspeed_deg_s": 1.0,
                    },
                },
                "publish_status": {
                    "last_publish_success": True,
                    "command_publication_source": "offboard_commander",
                },
                "publish_success": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_gazebo_visual_artifact_content_checks_accept_strict_evidence(tmp_path):
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "gazebo_visual_validation.json")
    run_dir = tmp_path / "run"
    write_valid_gazebo_visual_evidence(run_dir)

    checks = harness.artifact_content_checks(plan, run_dir)

    assert checks["px4_container_metadata"]["ok"] is True
    assert checks["px4_container_metadata"]["repo_digests"]
    assert checks["generated_receiver_proof_manifest"]["ok"] is True
    assert checks["gazebo_receiver_pipeline"]["ok"] is True
    assert checks["gazebo_frame_hashes"]["ok"] is True
    assert checks["tracker_command_trace"]["ok"] is True
    assert checks["offboard_publish_trace"]["ok"] is True


def test_gazebo_visual_artifact_content_checks_reject_weak_evidence(tmp_path):
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "gazebo_visual_validation.json")
    run_dir = tmp_path / "run"
    (run_dir / "video").mkdir(parents=True)
    (run_dir / "trace").mkdir(parents=True)
    (run_dir / "px4").mkdir(parents=True)
    (run_dir / "px4" / "container_metadata.json").write_text(
        json.dumps(
            {
                "collected": True,
                "image_inspect": {
                    "returncode": 0,
                    "stdout": json.dumps([{"Id": "sha256:image", "RepoDigests": []}]),
                },
                "container_inspect": None,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "video" / "generated_receiver_proof_manifest.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "mode": "dry_run",
                "fresh_ok": False,
                "stale_unusable_ok": False,
                "dimensions_ok": False,
                "fresh_frame_count": 0,
                "receiver_pipeline": "udpsrc ! rtph264depay ! appsink",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "video" / "gazebo_receiver_pipeline.txt").write_text(
        "udpsrc ! rtph264depay ! appsink",
        encoding="utf-8",
    )
    (run_dir / "video" / "gazebo_frame_hashes.json").write_text(
        json.dumps({"all": []}),
        encoding="utf-8",
    )
    (run_dir / "trace" / "tracker_command_trace.jsonl").write_text("", encoding="utf-8")
    (run_dir / "trace" / "offboard_publish_trace.jsonl").write_text(
        "{not-json}\n",
        encoding="utf-8",
    )

    checks = harness.artifact_content_checks(plan, run_dir)

    assert checks["px4_container_metadata"]["ok"] is False
    assert checks["px4_container_metadata"]["digest_required_ok"] is False
    assert checks["px4_container_metadata"]["require_container_metadata"] is True
    assert checks["generated_receiver_proof_manifest"]["ok"] is False
    assert checks["gazebo_receiver_pipeline"]["ok"] is False
    assert checks["gazebo_frame_hashes"]["ok"] is False
    assert checks["tracker_command_trace"]["ok"] is False
    assert checks["offboard_publish_trace"]["ok"] is False


def test_gazebo_visual_trace_validator_rejects_non_normalized_trace_records(tmp_path):
    harness = load_harness_module()
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        json.dumps({"timestamp": 1.0, "frame_index": 0, "target": {"bbox": [1, 2, 3, 4]}})
        + "\n",
        encoding="utf-8",
    )

    result = harness.validate_trace_jsonl(
        trace,
        expected_record_type="tracker_command",
    )

    assert result["ok"] is False
    assert any("record_type" in error["error"] for error in result["schema_errors"])
    assert any("command_intent" in error["error"] for error in result["schema_errors"])


def mavlink_anywhere_probe_results(
    plan,
    endpoints_payload,
    *,
    text=None,
    profile_overrides=None,
):
    payload_text = text if text is not None else json.dumps(endpoints_payload)
    profile_json = {
        "schema": "sidecar-profile/v1",
        "backend": "mavlink-anywhere",
        "source": "node-local",
        "present": True,
        "hash": "fixture-hash",
        "profile_count": len(endpoints_payload.get("endpoints", [])),
        "endpoints": endpoints_payload.get("endpoints", []),
    }
    if profile_overrides:
        profile_json.update(profile_overrides)
    return {
        "route_map/mavlink_anywhere_endpoints.json": {
            "raw": {
                "ok": True,
                "status": 200,
                "json": endpoints_payload,
                "text": payload_text,
            }
        },
        "route_map/mavlink_anywhere_config.json": {
            "raw": {
                "ok": True,
                "status": 200,
                "json": endpoints_payload,
                "text": payload_text,
            }
        },
        "route_map/mavlink_anywhere_profiles_summary.json": {
            "raw": {
                "ok": True,
                "status": 200,
                "json": profile_json,
                "text": payload_text,
            }
        },
        "probes/pixeagle_current_config.json": {
            "raw": {
                "ok": True,
                "status": 200,
                "json": {"config": plan["stack"]["pixeagle"]["required_config"]},
                "text": "{}",
            }
        },
    }


def test_structured_mavlink_anywhere_endpoint_validation_passes_with_typed_routes():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    endpoints_payload = {
        "endpoints": [
            {
                "name": "mavsdk",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 14540,
                "category": "local",
                "enabled": True,
            },
            {
                "name": "mavlink2rest",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 14569,
                "category": "local",
                "enabled": True,
            },
            {
                "name": "local_mavlink",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 12550,
                "category": "local",
                "enabled": True,
            },
        ]
    }

    checks = harness.semantic_stack_checks(
        plan, mavlink_anywhere_probe_results(plan, endpoints_payload)
    )
    route_check = checks["mavlink_anywhere_required_outputs"]

    assert route_check["ok"] is True
    assert route_check["validation"] == "structured_endpoint_objects"
    assert route_check["missing_outputs"] == []
    assert route_check["parsed_endpoint_counts"] == {
        "endpoints": 3,
        "config": 3,
        "profiles_summary": 3,
    }
    assert len(route_check["matched_outputs"]) == 3


def test_structured_mavlink_anywhere_endpoint_validation_rejects_text_only_matches():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    incidental_text = "127.0.0.1:14540 127.0.0.1:14569 127.0.0.1:12550"

    checks = harness.semantic_stack_checks(
        plan,
        mavlink_anywhere_probe_results(
            plan,
            {"endpoints": []},
            text=incidental_text,
        ),
    )
    route_check = checks["mavlink_anywhere_required_outputs"]

    assert route_check["ok"] is False
    assert route_check["validation"] == "structured_endpoint_objects"
    assert sorted(item["endpoint"] for item in route_check["missing_outputs"]) == sorted(
        plan["stack"]["routing"]["required_outputs"]
    )
    assert route_check["parsed_endpoint_counts"] == {
        "endpoints": 0,
        "config": 0,
        "profiles_summary": 0,
    }


def test_structured_mavlink_anywhere_endpoint_validation_rejects_address_port_only_json():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    incomplete_payload = {
        "endpoints": [
            {"address": "127.0.0.1", "port": 14540},
            {"address": "127.0.0.1", "port": 14569},
            {"address": "127.0.0.1", "port": 12550},
        ]
    }

    checks = harness.semantic_stack_checks(
        plan, mavlink_anywhere_probe_results(plan, incomplete_payload)
    )
    route_check = checks["mavlink_anywhere_required_outputs"]

    assert route_check["ok"] is False
    assert sorted(item["endpoint"] for item in route_check["missing_outputs"]) == sorted(
        plan["stack"]["routing"]["required_outputs"]
    )
    assert route_check["parsed_endpoint_counts"] == {
        "endpoints": 0,
        "config": 0,
        "profiles_summary": 0,
    }


def test_structured_mavlink_anywhere_endpoint_validation_rejects_disabled_routes():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    endpoints_payload = {
        "endpoints": [
            {
                "name": "mavsdk",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 14540,
                "category": "local",
                "enabled": False,
            },
            {
                "name": "mavlink2rest",
                "type": "UdpEndpoint",
                "mode": "server",
                "address": "127.0.0.1",
                "port": 14569,
                "category": "local",
                "enabled": True,
            },
            {
                "name": "local_mavlink",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 12550,
                "category": "local",
                "enabled": True,
            },
        ]
    }

    checks = harness.semantic_stack_checks(
        plan, mavlink_anywhere_probe_results(plan, endpoints_payload)
    )
    route_check = checks["mavlink_anywhere_required_outputs"]

    assert route_check["ok"] is False
    assert {"127.0.0.1:14540", "127.0.0.1:14569"} == {
        item["endpoint"] for item in route_check["missing_outputs"]
    }
    assert [item["endpoint"] for item in route_check["matched_outputs"]] == [
        "127.0.0.1:12550"
    ]


def test_structured_mavlink_anywhere_endpoint_validation_requires_profile_metadata():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    endpoints_payload = {
        "endpoints": [
            {
                "name": "mavsdk",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 14540,
                "category": "local",
                "enabled": True,
            },
            {
                "name": "mavlink2rest",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 14569,
                "category": "local",
                "enabled": True,
            },
            {
                "name": "local_mavlink",
                "type": "UdpEndpoint",
                "mode": "normal",
                "address": "127.0.0.1",
                "port": 12550,
                "category": "local",
                "enabled": True,
            },
        ]
    }

    checks = harness.semantic_stack_checks(
        plan,
        mavlink_anywhere_probe_results(
            plan,
            endpoints_payload,
            profile_overrides={"backend": "unexpected-sidecar", "present": False},
        ),
    )
    route_check = checks["mavlink_anywhere_required_outputs"]

    assert route_check["ok"] is False
    assert route_check["missing_outputs"] == []
    assert {
        (
            mismatch["path"],
            mismatch["expected"],
            mismatch["actual"],
        )
        for mismatch in route_check["profile_metadata_mismatches"]
    } == {
        (
            "route_map/mavlink_anywhere_profiles_summary.json.backend",
            "mavlink-anywhere",
            "unexpected-sidecar",
        ),
        (
            "route_map/mavlink_anywhere_profiles_summary.json.present",
            True,
            False,
        ),
    }


def test_phase2_plan_declares_executable_scenario_actions():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    summary = harness.summarize_scenario_actions(plan)

    assert summary["scenario_count"] == len(plan["scenarios"])
    assert summary["total_actions"] >= len(plan["scenarios"])
    assert summary["control_actions"] >= 2
    assert summary["manual_fault_actions"] == 0
    for scenario in plan["scenarios"]:
        assert scenario["actions"], f"{scenario['id']} has no scenario actions"
        if not any(action["type"] == "manual_fault" for action in scenario["actions"]):
            assert any(
                harness.action_has_substantive_assertion(action)
                for action in scenario["actions"]
                if action["type"] == "http_request"
            ), f"{scenario['id']} lacks a runtime equality assertion"


def test_phase2_target_loss_uses_owned_tracker_output_injector():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    scenario = next(item for item in plan["scenarios"] if item["id"] == "target_loss")
    action = next(item for item in scenario["actions"] if item["id"] == "inject_target_loss")

    assert plan["stack"]["pixeagle"]["required_environment"] == {
        "PIXEAGLE_ENABLE_SITL_INJECTIONS": "1"
    }
    assert (
        plan["stack"]["pixeagle"]["required_config"]["Follower.FOLLOWER_MODE"]
        == "mc_velocity_position"
    )
    assert action["type"] == "http_request"
    assert action["method"] == "POST"
    assert action["target"] == "pixeagle"
    assert action["path"] == "/api/v1/sitl/injections/tracker-output"
    assert action["control_action"] is True
    assert action["expect_status"] == [202]
    assert action["json_body"]["usable_for_following"] is False
    assert action["json_body"]["data_is_stale"] is True
    assert action["json_body"]["freshness_reason"] == "sitl_target_loss"
    assert any(
        expectation.get("path") == "injection.processed_tracking_active"
        and expectation.get("equals") is False
        for expectation in action["expect_json"]
    )
    assert {
        ("command_intent.reason", "mc_velocity_position_inactive_hold"),
        ("command_intent.fields.vel_body_down", 0.0),
        ("command_intent.fields.yawspeed_deg_s", 0.0),
        ("offboard_commander.running", True),
        ("offboard_commander.command_publication_source", "offboard_commander"),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in action["expect_json"]
    }

    post_loss = next(item for item in scenario["actions"] if item["id"] == "post_loss_setpoints")
    assert {
        ("setpoints.vel_body_down", 0.0),
        ("setpoints.yawspeed_deg_s", 0.0),
        ("command_publication.source", "offboard_commander"),
        ("command_publication.offboard_commander.running", True),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in post_loss["expect_json"]
    }


def test_phase2_heartbeat_and_setpoint_scenarios_assert_publication_evidence():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    heartbeat = next(item for item in plan["scenarios"] if item["id"] == "offboard_heartbeat")
    status_before = next(
        item for item in heartbeat["actions"]
        if item["id"] == "status_before_hold"
    )
    setpoints_after = next(
        item for item in heartbeat["actions"]
        if item["id"] == "setpoints_after_hold"
    )
    assert {
        ("offboard_commander.running", "equals", True),
        ("offboard_commander.command_rate_hz", "is_finite", True),
    } <= {
        (
            expectation.get("path"),
            "is_finite" if expectation.get("is_finite") is True else "equals",
            expectation.get("is_finite", expectation.get("equals")),
        )
        for expectation in status_before["expect_json"]
    }
    assert {
        ("command_publication.commands_sent_to_px4", "equals", True),
        ("command_publication.offboard_commander.sends_mavsdk_commands", "equals", True),
        ("command_publication.offboard_commander.last_publish_success", "equals", True),
        ("command_publication.offboard_commander.last_publish_monotonic_s", "is_finite", True),
    } <= {
        (
            expectation.get("path"),
            "is_finite" if expectation.get("is_finite") is True else "equals",
            expectation.get("is_finite", expectation.get("equals")),
        )
        for expectation in setpoints_after["expect_json"]
    }
    assert {
        ("command_publication.offboard_commander.publish_count", 1),
        ("command_publication.offboard_commander.successful_publishes", 1),
    } <= {
        (expectation.get("path"), expectation.get("greater_than_or_equal"))
        for expectation in setpoints_after["expect_json"]
    }

    follower_setpoints = next(
        item for item in plan["scenarios"] if item["id"] == "follower_setpoints"
    )
    snapshot = next(
        item for item in follower_setpoints["actions"]
        if item["id"] == "follower_setpoint_snapshot"
    )
    assert {
        ("control_type", "velocity_body_offboard"),
        ("profile", "mc_velocity_position"),
        ("command_publication.commands_sent_to_px4", True),
        ("command_publication.offboard_commander.sends_mavsdk_commands", True),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in snapshot["expect_json"]
    }
    assert {
        "setpoints.vel_body_fwd",
        "setpoints.vel_body_right",
        "setpoints.vel_body_down",
        "setpoints.yawspeed_deg_s",
    } <= {
        expectation.get("path")
        for expectation in snapshot["expect_json"]
        if expectation.get("is_finite") is True
    }


def test_phase2_video_stall_uses_owned_frame_stall_injector():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    scenario = next(item for item in plan["scenarios"] if item["id"] == "video_stall")
    action = next(item for item in scenario["actions"] if item["id"] == "inject_video_stall")

    assert action["type"] == "http_request"
    assert action["method"] == "POST"
    assert action["target"] == "pixeagle"
    assert action["path"] == "/api/v1/sitl/injections/video-stall"
    assert action["control_action"] is True
    assert action["expect_status"] == [202]
    assert action["json_body"]["usable_for_following"] is False
    assert action["json_body"]["reason"] == "sitl_video_stall"
    assert {
        ("injection.tracker_requires_video", True),
        ("injection.frame_status.usable_for_following", False),
        ("injection.frame_status.reason", "sitl_video_stall"),
        ("command_intent.reason", "mc_velocity_position_inactive_hold"),
        ("command_intent.fields.vel_body_down", 0.0),
        ("command_intent.fields.yawspeed_deg_s", 0.0),
        ("offboard_commander.running", True),
        ("offboard_commander.command_publication_source", "offboard_commander"),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in action["expect_json"]
    }

    post_stall = next(item for item in scenario["actions"] if item["id"] == "post_stall_setpoints")
    assert {
        ("setpoints.vel_body_down", 0.0),
        ("setpoints.yawspeed_deg_s", 0.0),
        ("command_publication.source", "offboard_commander"),
        ("command_publication.offboard_commander.running", True),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in post_stall["expect_json"]
    }


def test_phase2_commander_publish_failure_uses_owned_injector():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    scenario = next(
        item for item in plan["scenarios"] if item["id"] == "commander_publish_failure"
    )
    action = next(
        item for item in scenario["actions"]
        if item["id"] == "inject_commander_publish_failure"
    )

    assert action["type"] == "http_request"
    assert action["method"] == "POST"
    assert action["target"] == "pixeagle"
    assert action["path"] == "/api/v1/sitl/injections/commander-publish-failure"
    assert action["control_action"] is True
    assert action["expect_status"] == [202]
    assert action["json_body"]["failure_mode"] == "recorded_failure"
    assert action["json_body"]["failure_count"] == 3
    assert action["json_body"]["reason"] == "sitl_commander_publish_failure"
    expectations = [
        (expectation.get("path"), expectation.get("equals"))
        for expectation in action["expect_json"]
    ]
    assert {
        ("following_active", False),
        ("injection.failure_mode", "recorded_failure"),
        ("injection.applied_failure_count", 3),
        ("offboard_commander_before.running", True),
        ("offboard_commander_before.failure_policy_triggered", False),
        ("offboard_commander_after.running", False),
        ("offboard_commander_after.health_state", "failed"),
        ("offboard_commander_after.consecutive_failures", 3),
        ("offboard_commander_after.command_failure_threshold", 3),
        ("offboard_commander_after.last_publish_success", False),
        ("offboard_commander_after.failure_policy_triggered", True),
        ("offboard_commander_after.failure_policy_trigger_count", 1),
        ("offboard_commander_after.command_publication_source", "offboard_commander"),
        ("offboard_commander_failure.failure_policy_triggered", True),
        ("offboard_commander_failure.consecutive_failures", 3),
    } <= set(
        item for item in expectations
        if not isinstance(item[1], list)
    )
    assert any(
        expectation.get("path") == "disconnect_result.errors"
        and expectation.get("equals") == []
        for expectation in action["expect_json"]
    )

    post_status = next(
        item for item in scenario["actions"]
        if item["id"] == "post_publish_failure_status"
    )
    assert post_status["path"] == "/status"
    assert {
        ("following_active", False),
        ("offboard_commander_failure.failure_policy_triggered", True),
        ("offboard_commander_failure.consecutive_failures", 3),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in post_status["expect_json"]
    }


def test_phase2_mavlink2rest_timeout_uses_owned_local_timeout_injector():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    scenario = next(
        item for item in plan["scenarios"] if item["id"] == "mavlink2rest_timeout"
    )
    pre_status = next(
        item for item in scenario["actions"]
        if item["id"] == "pre_timeout_status"
    )
    action = next(
        item for item in scenario["actions"]
        if item["id"] == "inject_mavlink2rest_timeout"
    )

    assert pre_status["path"] == "/status"
    assert {
        ("mavlink_telemetry.status", "fresh"),
        ("mavlink_telemetry.connection_state", "connected"),
        ("mavlink_telemetry.fresh", True),
        ("mavlink_telemetry.endpoint", "http://127.0.0.1:8088"),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in pre_status["expect_json"]
    }
    assert any(
        expectation.get("path") == "mavlink_telemetry.last_success_age_s"
        and expectation.get("exists") is True
        for expectation in pre_status["expect_json"]
    )

    assert action["type"] == "http_request"
    assert action["method"] == "POST"
    assert action["target"] == "pixeagle"
    assert action["path"] == "/api/v1/sitl/injections/mavlink2rest-timeout"
    assert action["control_action"] is True
    assert action["expect_status"] == [202]
    assert action["json_body"]["failure_count"] == 2
    assert action["json_body"]["reason"] == "sitl_mavlink2rest_timeout"
    assert action["json_body"]["force_stale"] is True
    assert action["json_body"]["timeout_window_s"] == 5.0

    expectations = {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in action["expect_json"]
    }
    assert {
        ("status", "accepted"),
        ("accepted", True),
        ("injection.applied_failure_count", 2),
        ("injection.failure_reason", "sitl_mavlink2rest_timeout"),
        ("injection.force_stale", True),
        ("injection.timeout_window_s", 5.0),
        ("mavlink_telemetry.status", "stale"),
        ("mavlink_telemetry.connection_state", "error"),
        ("mavlink_telemetry.fresh", False),
        (
            "mavlink_telemetry.last_error",
            "Connection timeout - sitl_mavlink2rest_timeout",
        ),
        ("mavlink_telemetry.endpoint", "http://127.0.0.1:8088"),
        ("mavlink_telemetry.validation_timeout_active", True),
    } <= expectations

    post_status = next(
        item for item in scenario["actions"]
        if item["id"] == "post_timeout_status"
    )
    assert post_status["path"] == "/status"
    assert {
        ("mavlink_telemetry.status", "stale"),
        ("mavlink_telemetry.connection_state", "error"),
        ("mavlink_telemetry.fresh", False),
        (
            "mavlink_telemetry.last_error",
            "Connection timeout - sitl_mavlink2rest_timeout",
        ),
        ("mavlink_telemetry.validation_timeout_active", True),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in post_status["expect_json"]
    }

    service_probe = next(
        item for item in scenario["actions"]
        if item["id"] == "mavlink2rest_probe_after_timeout"
    )
    assert service_probe["target"] == "mavlink2rest"
    assert service_probe["path"] == "/v1/mavlink"
    assert service_probe["expect_status"] == [200]


def test_phase2_mavsdk_disconnect_uses_owned_local_disconnect_injector():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    scenario = next(
        item for item in plan["scenarios"] if item["id"] == "mavsdk_disconnect"
    )
    ensure_active = next(
        item for item in scenario["actions"]
        if item["id"] == "ensure_disconnect_following_active"
    )
    pre_status = next(
        item for item in scenario["actions"]
        if item["id"] == "pre_disconnect_status"
    )
    action = next(
        item for item in scenario["actions"]
        if item["id"] == "inject_mavsdk_disconnect"
    )

    assert ensure_active["type"] == "http_request"
    assert ensure_active["method"] == "POST"
    assert ensure_active["target"] == "pixeagle"
    assert ensure_active["path"] == "/commands/start_offboard_mode"
    assert ensure_active["control_action"] is True

    assert pre_status["path"] == "/status"
    assert {
        ("following_active", True),
        ("offboard_commander.running", True),
        ("offboard_commander.command_publication_source", "offboard_commander"),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in pre_status["expect_json"]
    }

    assert action["type"] == "http_request"
    assert action["method"] == "POST"
    assert action["target"] == "pixeagle"
    assert action["path"] == "/api/v1/sitl/injections/mavsdk-disconnect"
    assert action["control_action"] is True
    assert action["expect_status"] == [202]
    assert action["json_body"]["failure_mode"] == "local_mavsdk_command_disconnect"
    assert action["json_body"]["failure_count"] == 3
    assert action["json_body"]["reason"] == "sitl_mavsdk_disconnect"

    expectation_items = [
        (expectation.get("path"), expectation.get("equals"))
        for expectation in action["expect_json"]
    ]
    assert {
        ("status", "accepted"),
        ("accepted", True),
        ("following_active", False),
        ("injection.failure_mode", "local_mavsdk_command_disconnect"),
        ("injection.applied_failure_count", 3),
        ("injection.failure_reason", "sitl_mavsdk_disconnect"),
        ("px4_connection_before.connected", True),
        ("px4_connection_after.status", "validation_disconnected"),
        ("px4_connection_after.connected", False),
        ("px4_connection_after.validation_disconnect_active", True),
        ("px4_connection_after.disconnect_reason", "sitl_mavsdk_disconnect"),
        (
            "px4_connection_after.last_error",
            "MAVSDK disconnected - sitl_mavsdk_disconnect",
        ),
        ("offboard_commander_before.running", True),
        ("offboard_commander_before.failure_policy_triggered", False),
        ("offboard_commander_after.running", False),
        ("offboard_commander_after.health_state", "failed"),
        ("offboard_commander_after.consecutive_failures", 3),
        ("offboard_commander_after.last_publish_success", False),
        ("offboard_commander_after.last_publish_reason", "sitl_mavsdk_disconnect"),
        ("offboard_commander_after.failure_policy_triggered", True),
        ("offboard_commander_failure.failure_policy_triggered", True),
        ("offboard_commander_failure.last_publish_reason", "sitl_mavsdk_disconnect"),
    } <= set(
        item for item in expectation_items
        if not isinstance(item[1], list)
    )
    assert any(
        expectation.get("path") == "disconnect_result.errors"
        and expectation.get("equals") == [
            "Failed to stop offboard mode: MAVSDK disconnected - sitl_mavsdk_disconnect"
        ]
        for expectation in action["expect_json"]
    )

    post_status = next(
        item for item in scenario["actions"]
        if item["id"] == "post_disconnect_status"
    )
    assert {
        ("following_active", False),
        ("px4_connection.status", "validation_disconnected"),
        ("px4_connection.validation_disconnect_active", True),
        ("offboard_commander_failure.failure_policy_triggered", True),
        ("offboard_commander_failure.last_publish_reason", "sitl_mavsdk_disconnect"),
    } <= {
        (expectation.get("path"), expectation.get("equals"))
        for expectation in post_status["expect_json"]
    }


def test_sitl_plan_rejects_status_only_scenario_actions(tmp_path):
    harness = load_harness_module()
    plan = json.loads(
        (PLAN_DIR / "phase2_follower_validation.json").read_text(encoding="utf-8")
    )
    plan["scenarios"][0]["actions"] = [
        {
            "id": "weak_status_check",
            "type": "http_request",
            "method": "GET",
            "target": "pixeagle",
            "path": "/status",
            "expect_status": [200],
            "expect_json": [{"path": "following_active", "exists": True}],
        }
    ]
    weak_plan = tmp_path / "weak-plan.json"
    weak_plan.write_text(json.dumps(plan), encoding="utf-8")

    try:
        harness.load_plan(weak_plan)
    except harness.PlanError as exc:
        assert "HTTP status/existence checks alone" in str(exc)
    else:
        raise AssertionError("weak scenario action assertions should be rejected")


def test_gazebo_visual_plan_rejects_missing_visual_evidence_artifacts(tmp_path):
    harness = load_harness_module()
    plan = json.loads(
        (PLAN_DIR / "gazebo_visual_validation.json").read_text(encoding="utf-8")
    )
    plan["evidence_contract"] = [
        item for item in plan["evidence_contract"]
        if item != "video/gazebo_frame_hashes.json"
    ]
    weak_plan = tmp_path / "weak-gazebo-plan.json"
    weak_plan.write_text(json.dumps(plan), encoding="utf-8")

    try:
        harness.load_plan(weak_plan)
    except harness.PlanError as exc:
        assert "Gazebo visual evidence_contract missing artifacts" in str(exc)
        assert "video/gazebo_frame_hashes.json" in str(exc)
    else:
        raise AssertionError("Gazebo visual plans must declare frame-hash evidence")


def test_execute_px4_command_is_labeled_as_harness_managed():
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")

    container_name, command = harness.build_px4_container_command(
        plan,
        "test-run",
        image_override=None,
        model_override=None,
        container_name_override=None,
    )

    assert container_name == "pixeagle-px4-sitl-test-run"
    assert "--pull=never" in command
    assert f"{harness.MANAGED_CONTAINER_LABEL}=true" in command
    assert f"{harness.RUN_ID_CONTAINER_LABEL}=test-run" in command


def test_px4_evidence_imports_are_copied_and_checksumed(tmp_path):
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    params = tmp_path / "params.txt"
    ulog = tmp_path / "flight.ulg"
    tlog = tmp_path / "flight.tlog"
    params.write_text("SYS_AUTOSTART\t4001\n", encoding="utf-8")
    ulog.write_bytes(b"ulog-fixture")
    tlog.write_bytes(b"tlog-fixture")
    run_dir = tmp_path / "run"

    params_status = harness.collect_px4_params_artifact(run_dir, plan, str(params))
    ulog_status = harness.collect_px4_log_manifest(
        run_dir,
        plan,
        kind="ulog",
        input_files=[str(ulog)],
    )
    tlog_status = harness.collect_px4_log_manifest(
        run_dir,
        plan,
        kind="tlog",
        input_files=[str(tlog)],
    )

    assert params_status["collected"] is True
    assert ulog_status["collected"] is True
    assert tlog_status["collected"] is True
    assert (run_dir / "px4" / "params.txt").read_text(encoding="utf-8") == "SYS_AUTOSTART\t4001\n"

    ulog_manifest = json.loads((run_dir / "px4" / "ulog_manifest.json").read_text(encoding="utf-8"))
    tlog_manifest = json.loads((run_dir / "px4" / "tlog_manifest.json").read_text(encoding="utf-8"))
    assert ulog_manifest["collected"] is True
    assert tlog_manifest["collected"] is True
    assert ulog_manifest["entries"][0]["sha256"] == harness.sha256_file(ulog)
    assert tlog_manifest["entries"][0]["sha256"] == harness.sha256_file(tlog)
    assert (run_dir / ulog_manifest["entries"][0]["artifact_path"]).exists()
    assert (run_dir / tlog_manifest["entries"][0]["artifact_path"]).exists()


def test_px4_container_artifact_collection_copies_with_checksums(tmp_path, monkeypatch):
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    run_dir = tmp_path / "run"
    container_ref = "px4-container"
    container_files = {
        "/root/.px4/params.txt": b"SYS_AUTOSTART\t4001\n",
        "/root/.px4/log/flight.ulg": b"ulog-container-fixture",
        "/tmp/flight.tlog": b"tlog-container-fixture",
    }

    def fake_run_command(command, cwd, timeout_s=10.0):
        if command[:3] == ["docker", "exec", container_ref]:
            script = command[-1]
            if "*.ulg" in script:
                stdout = "/root/.px4/log/flight.ulg\n"
            elif "*.tlog" in script:
                stdout = "/tmp/flight.tlog\n"
            else:
                stdout = "/root/.px4/params.txt\n"
            return {"command": command, "returncode": 0, "stdout": stdout, "stderr": ""}
        if command[:2] == ["docker", "cp"]:
            source = command[2].split(":", 1)[1]
            target = Path(command[3])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(container_files[source])
            return {"command": command, "returncode": 0, "stdout": "", "stderr": ""}
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(harness, "run_command", fake_run_command)

    params_status = harness.collect_px4_params_artifact(
        run_dir,
        plan,
        None,
        container_ref=container_ref,
        auto_container_artifacts=True,
    )
    ulog_status = harness.collect_px4_log_manifest(
        run_dir,
        plan,
        kind="ulog",
        input_files=[],
        container_ref=container_ref,
        auto_container_artifacts=True,
    )
    tlog_status = harness.collect_px4_log_manifest(
        run_dir,
        plan,
        kind="tlog",
        input_files=[],
        container_ref=container_ref,
        auto_container_artifacts=True,
    )

    assert params_status["collected"] is True
    assert params_status["collection_source"] == "container_discovery"
    assert params_status["artifact"]["source_path"] == f"{container_ref}:/root/.px4/params.txt"
    assert (run_dir / "px4" / "params.txt").read_bytes() == container_files["/root/.px4/params.txt"]
    assert ulog_status["collected"] is True
    assert tlog_status["collected"] is True

    ulog_manifest = json.loads((run_dir / "px4" / "ulog_manifest.json").read_text(encoding="utf-8"))
    tlog_manifest = json.loads((run_dir / "px4" / "tlog_manifest.json").read_text(encoding="utf-8"))
    assert ulog_manifest["collection_sources"]["container_discovery"] is True
    assert tlog_manifest["collection_sources"]["container_discovery"] is True
    assert ulog_manifest["entries"][0]["source_path"] == f"{container_ref}:/root/.px4/log/flight.ulg"
    assert tlog_manifest["entries"][0]["source_path"] == f"{container_ref}:/tmp/flight.tlog"
    assert ulog_manifest["entries"][0]["sha256"] == harness.sha256_file(
        run_dir / ulog_manifest["entries"][0]["artifact_path"]
    )
    assert tlog_manifest["entries"][0]["sha256"] == harness.sha256_file(
        run_dir / tlog_manifest["entries"][0]["artifact_path"]
    )


def test_sitl_expectation_evaluator_supports_numeric_operators():
    harness = load_harness_module()
    payload = {
        "json": {
            "offboard_commander": {
                "publish_count": 3,
                "command_rate_hz": 20.0,
            }
        }
    }

    results = harness.evaluate_json_expectations(
        payload,
        [
            {"path": "offboard_commander.publish_count", "greater_than_or_equal": 1},
            {"path": "offboard_commander.publish_count", "less_than_or_equal": 100},
            {"path": "offboard_commander.command_rate_hz", "is_finite": True},
        ],
    )

    assert all(item["ok"] for item in results)


def test_px4_and_pixeagle_log_imports_are_copied(tmp_path):
    harness = load_harness_module()
    run_dir = tmp_path / "run"
    px4_log = tmp_path / "px4.log"
    pixeagle_log = tmp_path / "pixeagle.log"
    px4_log.write_text("px4 log\n", encoding="utf-8")
    pixeagle_log.write_text("pixeagle log\n", encoding="utf-8")

    px4_status = harness.collect_log_artifact(
        run_dir,
        relative_path="logs/px4_sitl.log",
        log_file=str(px4_log),
    )
    pixeagle_status = harness.collect_log_artifact(
        run_dir,
        relative_path="logs/pixeagle.log",
        log_file=str(pixeagle_log),
    )

    assert px4_status["collected"] is True
    assert pixeagle_status["collected"] is True
    assert (run_dir / "logs" / "px4_sitl.log").read_text(encoding="utf-8") == "px4 log\n"
    assert (run_dir / "logs" / "pixeagle.log").read_text(encoding="utf-8") == "pixeagle log\n"


def test_px4_sih_profile_script_defaults_to_side_effect_free_dry_run(tmp_path):
    artifact_root = tmp_path / "dry-run-artifacts"
    env = dict(os.environ)
    env["PYTHON_BIN"] = sys.executable

    result = subprocess.run(
        [
            "bash",
            str(SIH_PROFILE_SCRIPT),
            "--mode",
            "dry-run",
            "--artifact-root",
            str(artifact_root),
            "--run-scenarios",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["would_start_processes"] is False
    assert payload["would_run_scenarios_in_runtime_mode"] is True
    assert payload["operator_claim_boundary"] == (
        "Dry-run validates the plan only; it is not runtime evidence."
    )
    assert not artifact_root.exists()


def test_px4_sih_profile_script_runtime_modes_are_explicit_and_non_sudo():
    script = SIH_PROFILE_SCRIPT.read_text(encoding="utf-8")

    assert 'MODE="dry-run"' in script
    assert "--execute" in script
    assert "--allow-process-start" in script
    assert "--auto-px4-container-artifacts" in script
    assert "px4io/px4-sitl:v1.17.0" in script
    assert "sihsim_quadx" in script
    assert "sudo" not in script
    assert "configure_mavlink_router" not in script
    assert "docker pull" not in script


def test_px4_sih_workflow_is_opt_in_and_uploads_artifacts():
    workflow = SIH_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "scripts/sitl/run_px4_sih_profile.sh" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "if-no-files-found: ignore" in workflow
    assert "pull_px4_image" in workflow
    assert "docker pull \"$PX4_IMAGE\"" in workflow
    assert "env.SIH_MODE == 'execute-px4'" in workflow
    assert "Normal pull-request CI does not run this workflow." in workflow


def test_makefile_exposes_opt_in_sih_targets():
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert "sitl-sih-dry-run:" in makefile
    assert "sitl-sih-probe:" in makefile
    assert "sitl-sih-execute-px4:" in makefile
    assert "run_px4_sih_profile.sh --mode dry-run" in makefile
    assert "run_px4_sih_profile.sh --mode probe-only" in makefile
    assert "run_px4_sih_profile.sh --mode execute-px4" in makefile


def test_px4_gazebo_visual_profile_script_defaults_to_side_effect_free_dry_run(tmp_path):
    artifact_root = tmp_path / "gazebo-dry-run-artifacts"
    env = dict(os.environ)
    env["PYTHON_BIN"] = sys.executable

    result = subprocess.run(
        [
            "bash",
            str(GAZEBO_PROFILE_SCRIPT),
            "--mode",
            "dry-run",
            "--artifact-root",
            str(artifact_root),
            "--json",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["summary"]["plan"]["name"] == "gazebo_visual_validation"
    assert payload["would_start_processes"] is False
    assert payload["scenario_action_summary"]["manual_fault_actions"] == 0
    assert "video/gazebo_frame_hashes.json" in payload["summary"]["evidence_contract"]
    assert not artifact_root.exists()


def test_px4_gazebo_visual_profile_script_runtime_modes_are_explicit_and_non_sudo():
    script = GAZEBO_PROFILE_SCRIPT.read_text(encoding="utf-8")

    assert 'MODE="dry-run"' in script
    assert "execute-gazebo" in script
    assert "--execute" in script
    assert "--allow-process-start" in script
    assert "--auto-px4-container-artifacts" in script
    assert "--generated-receiver-proof-manifest" in script
    assert "--gazebo-receiver-pipeline" in script
    assert "--gazebo-frame-hashes" in script
    assert "--tracker-command-trace" in script
    assert "--offboard-publish-trace" in script
    assert "px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01" in script
    assert "gz_x500_mono_cam" in script
    assert "sudo" not in script
    assert "configure_mavlink_router" not in script
    assert "docker pull" not in script


def test_px4_gazebo_visual_workflow_is_opt_in_and_uploads_artifacts():
    workflow = GAZEBO_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "scripts/sitl/run_px4_gazebo_visual_profile.sh" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "if-no-files-found: ignore" in workflow
    assert "permissions:" in workflow
    assert "contents: read" in workflow
    assert "pull_px4_image" in workflow
    assert "generated_receiver_proof_manifest" in workflow
    assert "gazebo_receiver_pipeline" in workflow
    assert "gazebo_frame_hashes" in workflow
    assert "tracker_command_trace" in workflow
    assert "offboard_publish_trace" in workflow
    assert 'docker pull "$PX4_IMAGE"' in workflow
    assert "env.GAZEBO_MODE == 'execute-gazebo'" in workflow
    assert "Normal pull-request CI does not run this workflow." in workflow
    assert "retention-days: 14" in workflow
    assert "execute-gazebo" in workflow


def test_makefile_exposes_opt_in_gazebo_visual_targets():
    makefile = MAKEFILE.read_text(encoding="utf-8")

    assert "sitl-gazebo-dry-run:" in makefile
    assert "sitl-gazebo-probe:" in makefile
    assert "sitl-gazebo-execute-px4:" in makefile
    assert "run_px4_gazebo_visual_profile.sh --mode dry-run" in makefile
    assert "run_px4_gazebo_visual_profile.sh --mode probe-only" in makefile
    assert "run_px4_gazebo_visual_profile.sh --mode execute-gazebo" in makefile


def test_px4_container_artifact_find_command_is_read_only(monkeypatch):
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    recorded = {}

    def fake_run_command(command, cwd, timeout_s=10.0):
        recorded["command"] = command
        return {"command": command, "returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(harness, "run_command", fake_run_command)

    files, result = harness.find_px4_container_artifacts(
        plan,
        container_ref="px4-container",
        kind="ulog",
    )

    assert files == []
    assert result["returncode"] == 0
    command = recorded["command"]
    assert command[:3] == ["docker", "exec", "px4-container"]
    script = command[-1]
    assert "find" in script
    assert "docker" not in script
    assert ">" not in script
    for forbidden in (" stop ", " rm ", " restart ", " kill ", " mv "):
        assert forbidden not in f" {script} "


def test_probe_only_auto_px4_container_artifacts_requires_selector():
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-name",
            "phase2_follower_validation",
            "--probe-only",
            "--auto-px4-container-artifacts",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--px4-container-name or --px4-container-id" in result.stderr


def test_dry_run_with_auto_px4_container_artifacts_is_side_effect_free():
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-name",
            "phase2_follower_validation",
            "--dry-run",
            "--auto-px4-container-artifacts",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["would_start_processes"] is False


def test_probe_collection_with_container_name_without_auto_does_not_copy(tmp_path, monkeypatch):
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    run_dir = tmp_path / "run"
    commands = []

    def fake_run_command(command, cwd, timeout_s=10.0):
        commands.append(command)
        return {"command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

    def fake_http_get_json(url, timeout_s=5.0):
        payload = {}
        if url.endswith("/api/v1/status"):
            payload = {"text": "127.0.0.1:14540 127.0.0.1:14569 127.0.0.1:12550"}
        elif url.endswith("/api/config/current"):
            payload = {"config": plan["stack"]["pixeagle"]["required_config"]}
        return {"ok": True, "status": 200, "json": payload, "text": json.dumps(payload)}

    monkeypatch.setattr(harness, "run_command", fake_run_command)
    monkeypatch.setattr(harness, "http_get_json", fake_http_get_json)
    monkeypatch.setattr(harness, "current_git_metadata", lambda: {})
    monkeypatch.setattr(harness, "runtime_metadata", lambda: {})

    manifest = {"mode": "probe_only"}
    harness.collect_probe_artifacts(
        plan,
        run_dir,
        manifest,
        0.1,
        px4_container_name="operator-px4",
        auto_px4_container_artifacts=False,
    )

    assert any(command[:2] == ["docker", "inspect"] for command in commands)
    assert not any(command[:2] == ["docker", "exec"] for command in commands)
    assert not any(command[:2] == ["docker", "cp"] for command in commands)
    assert not any(command[:2] == ["docker", "stop"] for command in commands)
    assert manifest["px4_artifact_collection"]["auto_container_artifacts"] is False


def test_execute_auto_px4_container_artifacts_requires_verified_container_id():
    harness = load_harness_module()

    assert not harness.should_auto_collect_px4_container_artifacts(
        execute_mode=True,
        probe_only_mode=False,
        requested_auto_collection=True,
        px4_container_id=None,
        px4_container_name="stale-harness-name",
    )
    assert harness.should_auto_collect_px4_container_artifacts(
        execute_mode=True,
        probe_only_mode=False,
        requested_auto_collection=False,
        px4_container_id="verified-container-id",
        px4_container_name="harness-name",
    )
    assert harness.should_auto_collect_px4_container_artifacts(
        execute_mode=False,
        probe_only_mode=True,
        requested_auto_collection=True,
        px4_container_id=None,
        px4_container_name="operator-selected-container",
    )
    assert not harness.should_auto_collect_px4_container_artifacts(
        execute_mode=False,
        probe_only_mode=True,
        requested_auto_collection=False,
        px4_container_id=None,
        px4_container_name="operator-selected-container",
    )


def test_probe_collection_with_operator_auto_artifacts_never_stops_container(tmp_path, monkeypatch):
    harness = load_harness_module()
    plan = harness.load_plan(PLAN_DIR / "phase2_follower_validation.json")
    run_dir = tmp_path / "run"
    commands = []
    container_files = {
        "/root/.px4/params.txt": b"SYS_AUTOSTART\t4001\n",
        "/root/.px4/log/flight.ulg": b"ulog-container-fixture",
        "/tmp/flight.tlog": b"tlog-container-fixture",
    }

    def fake_run_command(command, cwd, timeout_s=10.0):
        commands.append(command)
        if command[:2] == ["docker", "cp"]:
            source = command[2].split(":", 1)[1]
            target = Path(command[3])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(container_files[source])
        if command[:3] == ["docker", "exec", "operator-px4"]:
            script = command[-1]
            if "*.ulg" in script:
                stdout = "/root/.px4/log/flight.ulg\n"
            elif "*.tlog" in script:
                stdout = "/tmp/flight.tlog\n"
            else:
                stdout = "/root/.px4/params.txt\n"
            return {"command": command, "returncode": 0, "stdout": stdout, "stderr": ""}
        return {"command": command, "returncode": 0, "stdout": "{}", "stderr": ""}

    def fake_http_get_json(url, timeout_s=5.0):
        payload = {}
        if url.endswith("/api/v1/status"):
            payload = {"text": "127.0.0.1:14540 127.0.0.1:14569 127.0.0.1:12550"}
        elif url.endswith("/api/config/current"):
            payload = {"config": plan["stack"]["pixeagle"]["required_config"]}
        return {"ok": True, "status": 200, "json": payload, "text": json.dumps(payload)}

    monkeypatch.setattr(harness, "run_command", fake_run_command)
    monkeypatch.setattr(harness, "http_get_json", fake_http_get_json)
    monkeypatch.setattr(harness, "current_git_metadata", lambda: {})
    monkeypatch.setattr(harness, "runtime_metadata", lambda: {})

    manifest = {"mode": "probe_only"}
    harness.collect_probe_artifacts(
        plan,
        run_dir,
        manifest,
        0.1,
        px4_container_name="operator-px4",
        auto_px4_container_artifacts=True,
    )

    assert any(command[:2] == ["docker", "exec"] for command in commands)
    assert any(command[:2] == ["docker", "cp"] for command in commands)
    assert not any(command[:2] == ["docker", "stop"] for command in commands)
    assert manifest["px4_artifact_collection"]["collection_mode"] == "operator_selected_container"
    assert manifest["artifact_status"]["px4/params.txt"]["collected"] is True
    assert manifest["artifact_status"]["px4/ulog_manifest.json"]["collected"] is True
    assert manifest["artifact_status"]["px4/tlog_manifest.json"]["collected"] is True


def test_runtime_scenario_failure_takes_precedence_over_incomplete_artifacts(tmp_path):
    base_plan = json.loads(
        (PLAN_DIR / "phase2_follower_validation.json").read_text(encoding="utf-8")
    )
    base_plan["stack"]["pixeagle"]["base_url"] = "http://127.0.0.1:9"
    base_plan["stack"]["mavlink2rest"]["url"] = "http://127.0.0.1:9"
    base_plan["stack"]["routing"]["dashboard_url"] = "http://127.0.0.1:9"
    plan_file = tmp_path / "failed-scenario-plan.json"
    plan_file.write_text(json.dumps(base_plan), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-file",
            str(plan_file),
            "--probe-only",
            "--run-scenarios",
            "--allow-control-actions",
            "--timeout-s",
            "0.01",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "failed-scenario",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["result"] == "failed"
    assert "Scenario failures take precedence" in payload["result_reason"]
    assert payload["scenario_execution"]["summary"]["result"] == "failed"


def test_sitl_harness_dry_run_is_side_effect_free_json():
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-name",
            "phase2_follower_validation",
            "--dry-run",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["would_start_processes"] is False
    assert payload["would_run_scenarios_in_runtime_mode"] is False
    assert payload["scenario_action_summary"]["scenario_count"] >= 1
    assert payload["summary"]["required_phase2_scenarios_missing"] == []


def test_sitl_harness_dry_run_reports_scenario_schedule_without_side_effects():
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-name",
            "phase2_follower_validation",
            "--dry-run",
            "--run-scenarios",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["mode"] == "dry_run"
    assert payload["would_start_processes"] is False
    assert payload["would_run_scenarios_in_runtime_mode"] is True
    assert payload["scenario_action_summary"]["control_actions"] >= 7
    assert payload["scenario_action_summary"]["manual_fault_actions"] == 0


def test_pytest_and_ci_keep_external_sitl_markers_opt_in():
    pytest_ini = (PROJECT_ROOT / "pytest.ini").read_text(encoding="utf-8")
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

    for marker in ("sitl", "px4", "e2e", "hardware", "manual"):
        assert f"    {marker}:" in pytest_ini

    external_filter = "not sitl and not px4 and not e2e and not hardware and not manual"
    assert external_filter in workflow
    assert external_filter in makefile


def test_probe_only_run_with_missing_stack_is_incomplete_and_nonzero(tmp_path):
    base_plan = json.loads(
        (PLAN_DIR / "phase2_follower_validation.json").read_text(encoding="utf-8")
    )
    base_plan["stack"]["pixeagle"]["base_url"] = "http://127.0.0.1:9"
    base_plan["stack"]["mavlink2rest"]["url"] = "http://127.0.0.1:9"
    base_plan["stack"]["routing"]["dashboard_url"] = "http://127.0.0.1:9"
    plan_file = tmp_path / "missing-stack-plan.json"
    plan_file.write_text(json.dumps(base_plan), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-file",
            str(plan_file),
            "--probe-only",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "missing-stack",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["result"] == "incomplete"
    assert "px4/ulog_manifest.json" in payload["missing_or_placeholder_artifacts"]
    assert "scenarios/scenario_results.json" in payload["missing_or_placeholder_artifacts"]
    assert payload["semantic_checks"]["mavlink_anywhere_required_outputs"]["ok"] is False
    assert payload["semantic_checks"]["pixeagle_required_config"]["ok"] is False


def test_probe_only_scenario_run_blocks_control_without_explicit_allowance(tmp_path):
    base_plan = json.loads(
        (PLAN_DIR / "phase2_follower_validation.json").read_text(encoding="utf-8")
    )
    base_plan["stack"]["pixeagle"]["base_url"] = "http://127.0.0.1:9"
    base_plan["stack"]["mavlink2rest"]["url"] = "http://127.0.0.1:9"
    base_plan["stack"]["routing"]["dashboard_url"] = "http://127.0.0.1:9"
    plan_file = tmp_path / "missing-stack-plan.json"
    plan_file.write_text(json.dumps(base_plan), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-file",
            str(plan_file),
            "--probe-only",
            "--run-scenarios",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "scenario-blocked",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 3, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["result"] == "failed"
    assert "Scenario failures take precedence" in payload["result_reason"]
    summary = payload["scenario_execution"]["summary"]
    assert summary["result"] in {"failed", "incomplete"}
    assert summary["blocked_actions"] >= 1

    scenario_results = json.loads(
        (
            tmp_path
            / "scenario-blocked-phase2_follower_validation"
            / "scenarios"
            / "scenario_results.json"
        ).read_text(encoding="utf-8")
    )
    blocked_actions = [
        action
        for scenario in scenario_results["scenarios"]
        for action in scenario["actions"]
        if action["result"] == "blocked"
    ]
    assert any(action["id"] == "request_offboard_start" for action in blocked_actions)


def test_probe_only_refuses_existing_artifact_directory(tmp_path):
    existing = tmp_path / "reuse-phase2_follower_validation"
    existing.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-name",
            "phase2_follower_validation",
            "--probe-only",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "reuse",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "refusing to reuse evidence" in result.stderr
