"""MC runner dry-run, staging and source-time contracts; no Docker or PX4 launches."""

from __future__ import annotations

import copy
import datetime as dt
import json
from types import SimpleNamespace

import pytest
import yaml

from tools import mc_follower_sih as runner
from tools import run_sih_follower_validation as entry
from tools import sih_isolated_host


def forbidden(*args, **kwargs):
    raise AssertionError("A dry-run/test tried to execute an external process")


def test_default_cli_is_read_only_even_with_an_output_path(tmp_path, monkeypatch, capsys):
    output = tmp_path / "never-created"
    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(sih_isolated_host, "host", forbidden)
    monkeypatch.setattr("sys.argv", ["runner", "--follower", "mc_velocity_position", "--evidence-root", str(output)])
    assert entry.main() == 0
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["mode"] == "dry_run"


def test_existing_archive_is_rejected_before_host_start(tmp_path, monkeypatch):
    monkeypatch.setattr(sih_isolated_host, "host", forbidden)
    marker = tmp_path / "keep"
    marker.write_text("existing evidence")
    monkeypatch.setattr("sys.argv", ["runner", "--execute", "--follower", "mc_velocity_position", "--evidence-root", str(tmp_path)])
    with pytest.raises(SystemExit):
        entry.main()
    assert marker.read_text() == "existing evidence"


def test_host_staging_preserves_actual_gains_limits_policy_and_altitude_mode(tmp_path, monkeypatch):
    captured = {}
    config = yaml.safe_load((runner.ROOT / "configs/config_default.yaml").read_text())
    config["Safety"]["GlobalLimits"]["MAX_VELOCITY_FORWARD"] = .31
    before = copy.deepcopy(config)

    def fake_host(args, *, driver_path, configure):
        (args.output / "backend/tools").mkdir(parents=True)
        configure(config)
        captured["scenario"] = yaml.safe_load((args.output / "scenario.yaml").read_text())
        captured["driver"] = driver_path

    monkeypatch.setattr(sih_isolated_host, "host", fake_host)
    args = SimpleNamespace(backend_repo=runner.ROOT, evidence_root=tmp_path / "staged",
                           follower="mc_velocity_position", enable_altitude_control=False)
    runner.run_host(args, entry.scenario_path(args.follower))
    assert captured["scenario"]["constraints"]["velocity"]["forward"] == .31
    assert captured["scenario"]["constraints"]["velocity"]["down"] == 0.
    assert captured["scenario"]["continuity_policy"] == {"mode": before["TargetContinuity"]["MODE"]}
    assert config["Safety"] == before["Safety"]
    assert config["PID"] == before["PID"]
    assert config["TargetContinuity"] == before["TargetContinuity"]
    assert config["MC_ATTITUDE_RATE"] == before["MC_ATTITUDE_RATE"]
    assert not config["Follower"]["FollowerOverrides"]["MC_VELOCITY_POSITION"]["ENABLE_ALTITUDE_CONTROL"]
    assert (args.output / "backend/tools/fixed_camera_world_target.py").is_file()


def test_explicit_altitude_flag_is_staged_truthfully_without_gain_changes(tmp_path, monkeypatch):
    config = yaml.safe_load((runner.ROOT / "configs/config_default.yaml").read_text())
    gains = copy.deepcopy(config["PID"])
    def fake_host(args, *, driver_path, configure):
        (args.output / "backend/tools").mkdir(parents=True)
        configure(config)
    monkeypatch.setattr(sih_isolated_host, "host", fake_host)
    args = SimpleNamespace(backend_repo=runner.ROOT, evidence_root=tmp_path / "staged",
                           follower="mc_velocity_ground", enable_altitude_control=True)
    runner.run_host(args, entry.scenario_path(args.follower))
    scenario = yaml.safe_load((args.output / "scenario.yaml").read_text())
    assert scenario["follower"]["altitude_control"]
    assert scenario["constraints"]["velocity"]["down"] == config["Safety"]["GlobalLimits"]["MAX_VELOCITY_VERTICAL"]
    assert config["MC_VELOCITY_GROUND"]["ENABLE_DESCEND_TO_TARGET"]
    assert config["PID"] == gains


def test_cached_pose_poll_is_skipped_without_extending_freshness():
    progress = runner.PoseProgress()
    assert progress.accept((100, 110), 10.)
    assert not progress.accept((100, 110), 10.05)
    assert not progress.accept((120, 110), 10.1)
    with pytest.raises(RuntimeError, match="expired"):
        progress.accept((120, 110), 10.51)


def test_new_pose_progress_recovers_but_backward_source_time_is_rejected():
    progress = runner.PoseProgress()
    assert progress.accept((100, 110), 10.)
    assert progress.accept((150, 160), 10.2)
    with pytest.raises(RuntimeError, match="backward"):
        progress.accept((149, 170), 10.3)


def test_partial_source_progress_cannot_hide_reordering_on_the_next_poll():
    progress = runner.PoseProgress()
    assert progress.accept((100, 110), 10.)
    assert not progress.accept((120, 110), 10.1)
    with pytest.raises(RuntimeError, match="backward"):
        progress.accept((115, 130), 10.2)


def test_missing_target_has_no_invented_image_measurement():
    output = runner.tracker_observation((.1, .2), measurement_epoch_s=100., measurement_monotonic_s=90., lost=True)
    assert not output.tracking_active
    assert output.position_2d is None
    assert "measurement_epoch_s" not in output.raw_data


def test_worker_refuses_host_namespace_before_importing_or_connecting(monkeypatch):
    monkeypatch.delenv("EVIDENCE_OWNER", raising=False)
    with pytest.raises(RuntimeError, match="owned loopback-only"):
        import asyncio
        asyncio.run(runner.worker(SimpleNamespace(follower="mc_velocity_position")))


def test_pose_observation_uses_raw_quaternion_and_independent_velocity():
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    def message(payload):
        return {"message": payload, "status": {"time": {"last_update": stamp}}}
    data = {"vehicles": {"1": {"id": 1, "components": {"1": {"id": 1, "messages": {
        "LOCAL_POSITION_NED": message(dict(type="LOCAL_POSITION_NED", time_boot_ms=1000,
            x=1., y=2., z=-20., vx=.1, vy=.2, vz=0.)),
        "ATTITUDE_QUATERNION": message(dict(type="ATTITUDE_QUATERNION", time_boot_ms=1005,
            q1=1., q2=0., q3=0., q4=0., repr_offset_q=[0., 1., 0., 0.])),
        "ATTITUDE": message(dict(type="ATTITUDE", time_boot_ms=1004, yaw=0.)),
    }}}}}}
    manager = SimpleNamespace(current_altitude=20., get_flight_mode_text=lambda _: "Hold")
    flight = dict(fresh=True, flight_mode=1, arm_status="Armed", landed_state="MAV_LANDED_STATE_IN_AIR")
    sample = runner.pose_observation(data, flight, manager, monotonic_s=42.)
    assert sample["quaternion_wxyz"] == (1., 0., 0., 0.)
    assert sample["velocity_ned"] == (.1, .2, 0.)
    assert sample["position_ned"] == (1., 2., -20.)
    assert sample["source_boot_ms"] == (1000, 1005)
    assert sample["monotonic_s"] == 42.


@pytest.mark.parametrize("ulog_present", [True, False])
def test_isolated_host_retains_logs_and_cleans_only_owned_network_namespaces(tmp_path, monkeypatch, ulog_present):
    repo = tmp_path / "source"
    (repo / "src/classes").mkdir(parents=True)
    (repo / "src/classes/app_controller.py").write_text("# staged test source\n")
    (repo / "tools").mkdir()
    (repo / "tools/sitl_gimbal_geometry_fixture.py").write_text("# staged test fixture\n")
    (repo / "configs").mkdir()
    (repo / "configs/config_default.yaml").write_bytes((runner.ROOT / "configs/config_default.yaml").read_bytes())
    (repo / "configs/config.yaml").write_text("operator_secret: never-copy\n")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    for name in ("mavsdk_server_bin", "mavlink2rest", "python"):
        (binary_dir / name).write_text("fixture binary")
    output = tmp_path / "evidence"
    calls, containers = [], {}

    def fake_command(*args, **kwargs):
        calls.append(args)
        if args[0] == "git":
            if "ls-files" in args:
                return "configs/config_default.yaml"
            return "" if "status" in args else "a" * 40
        if args[0] == str(binary_dir / "python"):
            return "[]"
        if args[:3] == ("docker", "image", "inspect"):
            return json.dumps([{"Id": "sha256:fixture"}])
        if args[:2] == ("docker", "run"):
            name = args[args.index("--name") + 1]
            label = args[args.index("--label") + 1].split("=", 1)
            containers[name] = {"Config": {"Labels": {label[0]: label[1]}}}
            return name
        if args[:2] == ("docker", "inspect"):
            (output / "result.json").write_text(json.dumps({"passed": True}))
            return json.dumps([{"State": {"Running": False, "ExitCode": 0}}])
        if args[:2] == ("docker", "exec"):
            return "/root/px4/log/test.ulg" if ulog_present else ""
        if args[:2] == ("docker", "stop"):
            return args[-1]
        raise AssertionError(args)

    def fake_run(args, **kwargs):
        calls.append(tuple(args))
        if args[:2] == ["docker", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps([containers[args[-1]]]))
        if args[:2] == ["docker", "cp"]:
            from pathlib import Path
            Path(args[-1]).write_bytes(b"synthetic test ULog artifact")
        elif args[:2] not in (["docker", "logs"], ["docker", "rm"]):
            raise AssertionError(args)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(sih_isolated_host, "command", fake_command)
    monkeypatch.setattr(sih_isolated_host.subprocess, "run", fake_run)
    args = SimpleNamespace(execute=True, backend_repo=repo, output=output,
        python=binary_dir / "python", bin_dir=binary_dir, opencv_lib=tmp_path,
        follower="mc_velocity_position", mount="HORIZONTAL")
    if ulog_present:
        sih_isolated_host.host(args, driver_path=runner.ROOT / "tools/mc_follower_sih.py")
    else:
        with pytest.raises(RuntimeError, match="artifact collection failed"):
            sih_isolated_host.host(args, driver_path=runner.ROOT / "tools/mc_follower_sih.py")
    launches = [call for call in calls if call[:2] == ("docker", "run")]
    assert len(launches) == 2
    assert launches[0][launches[0].index("--network") + 1] == "none"
    assert launches[1][launches[1].index("--network") + 1].startswith("container:")
    assert all(not ({"--privileged", "--device", "--publish", "-p"} & set(call)) for call in launches)
    assert len([call for call in calls if call[:3] == ("docker", "rm", "-f")]) == 2
    assert "operator_secret" not in (output / "configs/config.yaml").read_text()
    collection = json.loads((output / "artifact-collection.json").read_text())
    assert collection["passed"] == ulog_present
    if not ulog_present:
        assert not json.loads((output / "result.json").read_text())["passed"]
