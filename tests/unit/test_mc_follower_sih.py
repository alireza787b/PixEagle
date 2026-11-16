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


def test_owned_resolved_policy_is_report_input_and_cannot_be_an_authored_override(tmp_path):
    from tools.fixed_camera_world_target import MCScenario
    path = runner.ROOT / 'tools/sih_visualization_scenarios/gm_velocity_vector-qualification-horizontal-off.yaml'
    original = MCScenario.from_yaml(path)
    captured = yaml.safe_load(path.read_text())
    captured['continuity_policy'] = {'mode': 'bounded_decay'}
    captured['initial_conditions']['vehicle_ned'] = [1., 2., -20.]
    captured['constraints']['velocity']['forward'] = .37
    output = tmp_path / 'captured.yaml'
    output.write_text(yaml.safe_dump(captured))
    with pytest.raises(ValueError, match='cannot override saved continuity'):
        MCScenario.from_yaml(output)
    response = runner.captured_response_scenario(original, output)
    assert response.visual.continuity_policy == {'mode': 'bounded_decay'}
    assert response.visual.initial_vehicle_ned == (1., 2., -20.)
    assert response.visual.limits['velocity_forward'] == .37
    assert response.camera is original.camera
    assert response.minimum_vertical_response_m == original.minimum_vertical_response_m
    captured['follower']['altitude_control'] = True
    output.write_text(yaml.safe_dump(captured))
    with pytest.raises(ValueError, match='contract_changed'):
        runner.captured_response_scenario(original, output)


@pytest.mark.parametrize("hold,running,task_active,expected", [
    (True, False, False, True),
    (False, False, False, False),
    (True, True, False, False),
    (True, False, True, False),
    (True, None, False, False),
])
def test_release_evidence_requires_observed_hold_and_a_quiescent_publisher(hold, running, task_active, expected):
    row = runner.observed_command_release(
        {"hold": hold}, {"running": running, "task_active": task_active}, 12., 11.,
    )
    assert (row is not None) is expected
    if expected:
        assert row["command_owner_released_at"] == 11.
        assert row["timestamp"] == 12.
        assert row["command_expected"] is False


def test_telemetry_identity_is_requested_from_the_simulator_not_copied_from_command_link():
    from unittest.mock import Mock

    http = Mock()
    packet = {"header": {"system_id": 255}, "message": {"param2": 0.0}}
    http.get.return_value.json.return_value = packet
    runner.request_telemetry_identity(http)
    http.get.return_value.raise_for_status.assert_called_once_with()
    http.post.return_value.raise_for_status.assert_called_once_with()
    http.post.assert_called_once_with(
        "http://127.0.0.1:8088/v1/mavlink", timeout=2,
        json={"header": {"system_id": 255}, "message": {
            "param1": 148.0, "param2": 0.0,
            "command": {"type": "MAV_CMD_REQUEST_MESSAGE"},
            "target_system": 1, "target_component": 1,
        }},
    )


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


@pytest.mark.parametrize("telemetry_source", ["mavlink2rest", "mavsdk"])
def test_host_staging_preserves_actual_gains_limits_policy_and_altitude_mode(tmp_path, monkeypatch, telemetry_source):
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
                           follower="mc_velocity_position", enable_altitude_control=False,
                           telemetry_source=telemetry_source)
    runner.run_host(args, entry.scenario_path(args.follower))
    assert captured["scenario"]["constraints"]["velocity"]["forward"] == .31
    assert captured["scenario"]["constraints"]["velocity"]["down"] == 0.
    assert captured["scenario"]["continuity_policy"] == {"mode": before["TargetContinuity"]["MODE"]}
    assert config["Safety"] == before["Safety"]
    assert config["PID"] == before["PID"]
    assert config["TargetContinuity"] == before["TargetContinuity"]
    assert config["MC_ATTITUDE_RATE"] == before["MC_ATTITUDE_RATE"]
    assert config["Follower"]["USE_MAVLINK2REST"] == (telemetry_source == "mavlink2rest")
    assert json.loads((args.output / "harness-inputs.json").read_text())["control_telemetry_source"] == telemetry_source
    assert not config["Follower"]["FollowerOverrides"]["MC_VELOCITY_POSITION"]["ENABLE_ALTITUDE_CONTROL"]
    assert (args.output / "backend/tools/fixed_camera_world_target.py").is_file()


@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['horizontal', 'vertical'])
@pytest.mark.parametrize('altitude', [False, True])
def test_gimbal_staging_uses_declared_config_section_and_never_adopts_scenario_limits(
        tmp_path, monkeypatch, profile, mount, altitude):
    config = yaml.safe_load((runner.ROOT / 'configs/config_default.yaml').read_text())
    before = copy.deepcopy(config)
    def fake_host(args, *, driver_path, configure):
        (args.output / 'backend/tools').mkdir(parents=True)
        configure(config)
    monkeypatch.setattr(sih_isolated_host, 'host', fake_host)
    path = runner.ROOT / f'tools/sih_visualization_scenarios/{profile}-qualification-{mount}-{"on" if altitude else "off"}.yaml'
    args = SimpleNamespace(backend_repo=runner.ROOT, evidence_root=tmp_path / 'new', follower=profile,
                           enable_altitude_control=False, telemetry_source='mavlink2rest')
    runner.run_host(args, path)
    section = profile.upper()
    assert config['Follower']['FollowerOverrides'][section]['ENABLE_ALTITUDE_CONTROL'] is altitude
    assert config['GimbalTracker']['MOUNT_TYPE'] == mount.upper() == args.mount
    assert config['GimbalTracker']['ENABLED'] and not config['GimbalTracker']['CONTROL_ENABLED']
    assert config['Safety'] == before['Safety']
    assert config['PID'] == before['PID']
    assert config['TargetContinuity'] == before['TargetContinuity']
    inputs = json.loads((args.output / 'harness-inputs.json').read_text())
    assert inputs['fixture_kind'] == 'simulated_boresight'
    assert inputs['camera_projection'] is inputs['synthetic_image_size_px'] is None


def test_airborne_start_outside_saved_envelope_is_rejected_before_launch(tmp_path, monkeypatch):
    config = yaml.safe_load((runner.ROOT / "configs/config_default.yaml").read_text())
    config["Safety"]["GlobalLimits"]["MIN_ALTITUDE"] = 45.
    before = copy.deepcopy(config["Safety"])

    def configure_only(args, *, driver_path, configure):
        (args.output / "backend/tools").mkdir(parents=True)
        configure(config)
        pytest.fail("invalid airborne start must not reach simulator launch")

    monkeypatch.setattr(sih_isolated_host, "host", configure_only)
    args = SimpleNamespace(backend_repo=runner.ROOT, evidence_root=tmp_path / "staged",
                           follower="mc_velocity_position", enable_altitude_control=False)
    with pytest.raises(ValueError, match="outside the configured altitude envelope"):
        runner.run_host(args, entry.scenario_path(args.follower))
    assert config["Safety"] == before


def test_projected_image_keeps_real_synthetic_owner_and_original_measurement_receipt():
    from classes.app_controller import AppController
    from classes.frame_publisher import FramePublisher
    app = object.__new__(AppController)
    app.following_active = False
    app._tracking_session_generation = 4
    app.frame_publisher = FramePublisher()
    app.frame_publisher.invalidate_source('sih-test-pose-epoch')
    app.get_tracker_output = lambda: app._sih_tracker_output
    output = runner.tracker_observation((.25, -.5), measurement_epoch_s=100., measurement_monotonic_s=90.)
    sample = dict(monotonic_s=90., source_boot_ms=(100, 110))
    runner.bind_projected_image(app, output, sample, (20., 4., -20.))
    measurement = output.image_measurement
    assert measurement.pixel_xy == pytest.approx((400., 120.))
    assert measurement.provenance.source_id == app.frame_publisher.stream_id
    assert measurement.provenance.capture.captured_at == 90.
    assert measurement.provenance.calibration_revision is None
    assert app._guidance_source_readiness(output)['ready']
    app._freeze_following_observation_source()
    assert app.get_tracker_output().image_measurement is measurement
    app.frame_publisher.invalidate_source('replacement-sih-source')
    assert not app._guidance_source_readiness(output)['ready']


@pytest.mark.parametrize('coordinates', [(.37, -.23), (-.41, .62), (0., 0.), (-1., -1.)])
def test_asymmetric_synthetic_pixel_round_trip_uses_production_normalization(coordinates):
    from classes.frame_publisher import FramePublisher
    from classes.trackers.base_tracker import BaseTracker
    app = SimpleNamespace(frame_publisher=FramePublisher(), _tracking_session_generation=0)
    app.frame_publisher.invalidate_source('sih-grid-source')
    output = runner.tracker_observation(coordinates, measurement_epoch_s=100., measurement_monotonic_s=90.)
    runner.bind_projected_image(app, output, dict(monotonic_s=90., source_boot_ms=(100, 110)), (20., 4., -20.))
    tracker = SimpleNamespace(video_handler=SimpleNamespace(width=640, height=480))
    assert BaseTracker._normalize_center_static(tracker, output.image_measurement.pixel_xy) == pytest.approx(coordinates, abs=1e-15)


@pytest.mark.parametrize('coordinates', [(1., 0.), (0., 1.), (.999, 0.)])
def test_projection_outside_pixel_centre_grid_is_refused_without_clamping(coordinates):
    from classes.frame_publisher import FramePublisher
    app = SimpleNamespace(frame_publisher=FramePublisher(), _tracking_session_generation=0)
    app.frame_publisher.invalidate_source('sih-grid-source')
    output = runner.tracker_observation(coordinates, measurement_epoch_s=100., measurement_monotonic_s=90.)
    with pytest.raises(ValueError, match='image_pixel_outside_image'):
        runner.bind_projected_image(app, output, dict(monotonic_s=90., source_boot_ms=(100, 110)), (20., 4., -20.))
    assert output.position_2d == coordinates
    assert output.image_measurement is None
    assert not hasattr(app, 'tracking_input_context')


def test_explicit_altitude_flag_is_staged_truthfully_without_gain_changes(tmp_path, monkeypatch):
    config = yaml.safe_load((runner.ROOT / "configs/config_default.yaml").read_text())
    gains = copy.deepcopy(config["PID"])
    def fake_host(args, *, driver_path, configure):
        (args.output / "backend/tools").mkdir(parents=True)
        configure(config)
    monkeypatch.setattr(sih_isolated_host, "host", fake_host)
    args = SimpleNamespace(backend_repo=runner.ROOT, evidence_root=tmp_path / "staged",
                           follower="mc_velocity_ground", enable_altitude_control=True)
    runner.run_host(args, entry.scenario_path(args.follower, altitude_control=True))
    scenario = yaml.safe_load((args.output / "scenario.yaml").read_text())
    assert scenario["follower"]["altitude_control"]
    assert scenario["qualification"]["minimum_vertical_response_m"] == .1
    assert scenario["constraints"]["velocity"]["down"] == config["Safety"]["GlobalLimits"]["MAX_VELOCITY_VERTICAL"]
    assert config["MC_VELOCITY_GROUND"]["ENABLE_DESCEND_TO_TARGET"]
    assert config["PID"] == gains


@pytest.mark.parametrize("profile", sorted(entry.MC_PROFILES - {"mc_attitude_rate"}))
def test_altitude_flag_dry_run_and_execute_select_the_same_explicit_scenario(profile, tmp_path, monkeypatch, capsys):
    output = tmp_path / "never-created"
    monkeypatch.setattr(entry.subprocess, "run", forbidden)
    monkeypatch.setattr(sih_isolated_host, "host", forbidden)
    arguments = ["runner", "--follower", profile, "--enable-altitude-control", "--evidence-root", str(output)]
    monkeypatch.setattr("sys.argv", arguments)
    assert entry.main() == 0
    plan = json.loads(capsys.readouterr().out)["scenario"]
    assert plan["altitude_control"]
    assert any("0.1 m target-directed vertical closure" in requirement for requirement in plan["acceptance"])

    class WorkerPathCaptured(Exception):
        pass

    captured = {}
    def capture_worker_path(args, path):
        captured["path"] = path
        raise WorkerPathCaptured

    monkeypatch.setattr(runner, "run_host", capture_worker_path)
    monkeypatch.setattr("sys.argv", [*arguments, "--execute"])
    with pytest.raises(WorkerPathCaptured):
        entry.main()
    assert captured["path"] == entry.scenario_path(profile, altitude_control=True)
    assert captured["path"] != entry.scenario_path(profile)
    assert not output.exists()


@pytest.mark.parametrize("profile", sorted(entry.MC_PROFILES - {"mc_attitude_rate"}))
def test_altitude_flag_rejects_explicit_altitude_off_velocity_scenario(profile, monkeypatch):
    monkeypatch.setattr(sih_isolated_host, "host", forbidden)
    monkeypatch.setattr("sys.argv", ["runner", "--follower", profile, "--enable-altitude-control",
                                     "--scenario", str(entry.scenario_path(profile))])
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code == 2


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


def fault_scenario(tmp_path, fault, *, expected_handoff=False, profile='gm_velocity_vector', mount='horizontal', altitude=False):
    from tools.fixed_camera_world_target import MCScenario
    path = runner.ROOT / f'tools/sih_visualization_scenarios/{profile}-qualification-{mount}-{"on" if altitude else "off"}.yaml'
    if runner.mc_input_family(profile) == 'image':
        path = entry.scenario_path(profile, altitude)
    raw = yaml.safe_load(path.read_text())
    raw['faults'] = [fault]
    raw['qualification']['expected_handoff'] = expected_handoff
    path = tmp_path / 'fault.yaml'
    path.write_text(yaml.safe_dump(raw))
    return MCScenario.from_yaml(path)


def fault_checks(scenario, records, **overrides):
    values = dict(following_active=True, handoff=None, retarget_count=0,
        takeover_requested_at=None, mode_calls=[], telemetry_outage_injected=False)
    values.update(overrides)
    return runner.evaluate_fault_outcome(scenario, records, **values)


def received_row(elapsed, tracking, authority, *, reason=None):
    return dict(elapsed_s=elapsed, loss_active=tracking == 'TARGET_LOST',
        target_evidence_state='ABSENT' if tracking == 'TARGET_LOST' else 'CONFIRMED',
        gimbal_observation=dict(tracking_state=tracking),
        continuity=dict(authority_state=authority, reason_code=reason))


def test_scheduled_loss_or_unchanged_polls_cannot_prove_received_loss(tmp_path):
    scenario = fault_scenario(tmp_path, dict(kind='target_loss', at_s=8., duration_s=1.))
    scheduled_only = [dict(received_row(8.1, 'TRACKING_ACTIVE', 'ACTIVE'), scheduled_loss_active=True)]
    assert not fault_checks(scenario, scheduled_only)['expected_faults_executed']
    assert not fault_checks(scenario, [])['expected_faults_executed']


@pytest.mark.parametrize('missing', ['lost', 'reacquiring', 'restored', None])
def test_loss_recovery_requires_received_loss_confirmation_and_restoration(tmp_path, missing):
    scenario = fault_scenario(tmp_path, dict(kind='target_loss', at_s=8., duration_s=1.))
    rows = dict(lost=received_row(8.1, 'TARGET_LOST', 'COASTING'),
        reacquiring=received_row(9.1, 'TRACKING_ACTIVE', 'REACQUIRING'),
        restored=received_row(10.3, 'TRACKING_ACTIVE', 'ACTIVE'))
    result = fault_checks(scenario, [row for key, row in rows.items() if key != missing])
    assert all(result.values()) is (missing is None)


@pytest.mark.parametrize('reason,active,expected', [
    ('operator_stop', False, False), ('maximum_coast_time_reached', True, False),
    ('following_observation_source_changed', False, False), ('maximum_coast_time_reached', False, True),
])
def test_loss_handoff_must_be_fault_caused_before_operator_cleanup(tmp_path, reason, active, expected):
    scenario = fault_scenario(tmp_path, dict(kind='target_loss', at_s=8., duration_s=9.), expected_handoff=True)
    result = fault_checks(scenario, [received_row(8.1, 'TARGET_LOST', 'COASTING')],
        following_active=active, handoff=dict(reason_code=reason, result='confirmed_hold'))
    assert result['fault_handoff_before_operator_cleanup'] is expected


def test_gimbal_bounded_loss_cannot_pass_with_immediate_compatibility_handoff(tmp_path):
    scenario = fault_scenario(tmp_path, dict(kind='target_loss', at_s=8., duration_s=9.), expected_handoff=True)
    result = fault_checks(scenario, [received_row(8.1, 'TARGET_LOST', 'HANDOFF_PENDING')],
        following_active=False, handoff=dict(reason_code='tracker_unusable_for_following', result='confirmed_hold'))
    assert not result['fault_handoff_before_operator_cleanup']


def configured_gimbal_policy():
    from dataclasses import asdict
    from classes.target_continuity import ContinuityPolicy
    config = yaml.safe_load((runner.ROOT / 'configs/config_default.yaml').read_text())
    return json.loads(json.dumps(asdict(ContinuityPolicy.resolve(config['TargetContinuity'], 'gm_velocity_vector'))))


def budget_tracker(policy, reason='maximum_coast_time_reached', *, elapsed=8., distance=1.):
    return dict(timestamp=16., tracker_output=dict(tracking_active=False, usable_for_following=False,
        gimbal_observation=dict(tracking_state='TARGET_LOST')), continuity=dict(
        authority_state='HANDOFF_PENDING', reason_code=reason, handoff_request=dict(reason_code=reason),
        effective_policy=copy.deepcopy(policy), loss_elapsed_s=elapsed, coast_distance_m=distance))


@pytest.mark.parametrize('change', ['missing_policy', 'compatibility', 'immediate', 'policy_mismatch',
                                  'no_terminal', 'too_early', 'bad_elapsed', 'bad_distance', 'genuine_time', 'genuine_travel'])
def test_gimbal_loss_requires_actual_exhaustion_of_the_captured_canonical_policy(tmp_path, change):
    scenario = fault_scenario(tmp_path, dict(kind='target_loss', at_s=8., duration_s=9.), expected_handoff=True)
    policy = configured_gimbal_policy()
    reason = 'maximum_coast_distance_reached' if change == 'genuine_travel' else 'maximum_coast_time_reached'
    row = budget_tracker(policy, reason, elapsed=3. if change == 'genuine_travel' else 8.,
                         distance=4. if change == 'genuine_travel' else 1.)
    trackers = [row]
    if change == 'missing_policy':
        policy = None
    elif change == 'compatibility':
        policy['configuration_origin'] = 'compatibility_defaults'
    elif change == 'immediate':
        policy['mode'] = 'immediate_handoff'
    elif change == 'policy_mismatch':
        row['continuity']['effective_policy']['max_coast_time_s'] = 2.
    elif change == 'no_terminal':
        trackers = []
    elif change == 'too_early':
        row['continuity']['loss_elapsed_s'] = 1.
    elif change == 'bad_elapsed':
        row['continuity']['loss_elapsed_s'] = float('nan')
    elif change == 'bad_distance':
        row['continuity']['coast_distance_m'] = True
    result = fault_checks(scenario, [received_row(8.1, 'TARGET_LOST', 'COASTING')],
        following_active=False, handoff=dict(reason_code=reason, result='confirmed_hold'),
        configured_policy=policy, tracker_records=trackers)
    assert result['bounded_loss_budget_exhausted'] is change.startswith('genuine')
    assert all(result.values()) is change.startswith('genuine')


def test_legacy_image_immediate_loss_does_not_require_a_gimbal_budget(tmp_path):
    scenario = fault_scenario(tmp_path, dict(kind='target_loss', at_s=8., duration_s=1.),
                             expected_handoff=True, profile='mc_velocity_chase')
    result = fault_checks(scenario, [received_row(8.1, 'TARGET_LOST', 'HANDOFF_PENDING')],
        following_active=False, handoff=dict(reason_code='tracker_unusable_for_following', result='confirmed_hold'))
    assert all(result.values())
    assert 'bounded_loss_budget_exhausted' not in result


@pytest.mark.parametrize('change', ['missing', 'partial', 'deadline_extended', 'start_shifted', 'bad_type', None])
def test_retarget_budget_witness_is_exact_and_never_extends_a_pending_episode(change):
    before = dict(loss_started_at_monotonic_s=100., loss_deadline_monotonic_s=108.)
    after = dict(before)
    if change == 'missing':
        before = None
    elif change == 'partial':
        before.pop('loss_started_at_monotonic_s')
    elif change == 'deadline_extended':
        after['loss_deadline_monotonic_s'] += 1.
    elif change == 'start_shifted':
        after['loss_started_at_monotonic_s'] += 1.
    elif change == 'bad_type':
        after['loss_deadline_monotonic_s'] = '108'
    assert runner._retarget_budget_preserved(before, after, pending=True) is (change is None)


@pytest.mark.parametrize('angles', [True, False])
@pytest.mark.parametrize('change', ['missing', 'deadline_extended', 'restored_before_final', None])
def test_retained_gimbal_retarget_requires_budget_proof_and_final_target_restoration(tmp_path, angles, change):
    scenario = fault_scenario(tmp_path, dict(kind='retarget', at_s=8., target_offset_ned=[.5, .3, -.2]),
                             profile='gm_velocity_vector' if angles else 'mc_velocity_chase')
    before = dict(loss_started_at_monotonic_s=100., loss_deadline_monotonic_s=108.)
    event = dict(timestamp=8., event='retarget', before=dict(target_transition_pending=True, episode_id=1),
                 after=dict(target_transition_pending=True, episode_id=1), before_budget=before, after_budget=dict(before))
    if change == 'missing':
        event.pop('after_budget')
    elif change == 'deadline_extended':
        event['after_budget']['loss_deadline_monotonic_s'] += 1.
    result = dict(handoff=dict(reason_code='operator_stop', result='confirmed_hold'))
    evidence = dict(tracker=[], state=[dict(timestamp=7. if change == 'restored_before_final' else 10.,
                                          reason_code='target_authority_restored')])
    if angles and change is not None:
        with pytest.raises(ValueError, match='fault_outcome_unproven'):
            runner.validate_retained_fault_outcome(scenario.visual, result, evidence,
                expected_handoff=False, fault_events=[event])
    else:
        runner.validate_retained_fault_outcome(scenario.visual, result, evidence,
            expected_handoff=False, fault_events=[event])


@pytest.mark.parametrize('change', ['missing', 'final_mismatch', None])
def test_retained_gimbal_long_loss_requires_matching_captured_policy(tmp_path, change):
    scenario = fault_scenario(tmp_path, dict(kind='target_loss', at_s=8., duration_s=9.), expected_handoff=True)
    policy = configured_gimbal_policy()
    reason = 'maximum_coast_time_reached'
    tracker = budget_tracker(policy)
    result = dict(handoff=dict(reason_code=reason, result='confirmed_hold'))
    pre = dict(following_active=False, handoff=result['handoff'], checks=dict(bounded_loss_budget_exhausted=True))
    if change != 'missing':
        pre['configured_continuity_policy'] = policy
        result['configured_continuity_policy'] = copy.deepcopy(policy)
    if change == 'final_mismatch':
        result['configured_continuity_policy']['max_coast_time_s'] += 1.
    evidence = dict(tracker=[tracker], state=[])
    if change is not None:
        with pytest.raises(ValueError, match='fault_outcome_unproven'):
            runner.validate_retained_fault_outcome(scenario.visual, result, evidence,
                expected_handoff=True, fault_events=[], pre_cleanup=pre)
    else:
        runner.validate_retained_fault_outcome(scenario.visual, result, evidence,
            expected_handoff=True, fault_events=[], pre_cleanup=pre)


@pytest.mark.parametrize('extra', [None, 'action.hold', 'offboard.stop'])
@pytest.mark.parametrize('profile', ['gm_velocity_chase', 'gm_velocity_vector'])
@pytest.mark.parametrize('mount', ['horizontal', 'vertical'])
@pytest.mark.parametrize('altitude', [False, True])
def test_takeover_requires_one_actual_pilot_hold_and_no_additional_backend_mode_call(tmp_path, extra, profile, mount, altitude):
    scenario = fault_scenario(tmp_path, dict(kind='pilot_takeover', at_s=12.), expected_handoff=True,
                             profile=profile, mount=mount, altitude=altitude)
    calls = [dict(method='action.hold', monotonic_s=1.), dict(method='action.hold', monotonic_s=12.01)]
    if extra is not None:
        calls.append(dict(method=extra, monotonic_s=12.02))
    result = fault_checks(scenario, [], following_active=False,
        handoff=dict(reason_code='offboard_mode_exited', result='stopped'),
        takeover_requested_at=12., mode_calls=calls)
    assert result['takeover_no_backend_hold_or_offboard_stop'] is (extra is None)


@pytest.mark.asyncio
async def test_sdk_mode_observer_preserves_returns_exceptions_and_original_methods():
    from unittest.mock import AsyncMock
    hold, stop = AsyncMock(return_value='held'), AsyncMock(side_effect=RuntimeError('sdk refused'))
    drone = SimpleNamespace(action=SimpleNamespace(hold=hold), offboard=SimpleNamespace(stop=stop))
    calls = []
    with runner.observe_mode_calls(drone, calls.append):
        assert await drone.action.hold() == 'held'
        with pytest.raises(RuntimeError, match='sdk refused'):
            await drone.offboard.stop()
    assert [row['method'] for row in calls] == ['action.hold', 'offboard.stop']
    assert drone.action.hold is hold and drone.offboard.stop is stop
    hold.assert_awaited_once_with()
    stop.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_failed_diagnostic_recording_never_suppresses_sdk_mode_call():
    from unittest.mock import AsyncMock
    hold = AsyncMock(return_value='held')
    drone = SimpleNamespace(action=SimpleNamespace(hold=hold), offboard=SimpleNamespace(stop=AsyncMock()))
    def failed_record(_row):
        raise OSError('diagnostic storage unavailable')
    with runner.observe_mode_calls(drone, failed_record) as errors:
        assert await drone.action.hold() == 'held'
    assert errors == ['OSError']
    hold.assert_awaited_once_with()


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


def freshness_refusal_event():
    reason = "altitude_sample_unavailable"
    return dict(
        command_intent=SimpleNamespace(fields=dict(
            rollspeed_deg_s=0., pitchspeed_deg_s=0., yawspeed_deg_s=.5, thrust=.49,
        )),
        publication_attempted=False, submitted_fields=None,
        publish_status=dict(last_publish_success=False, terminal_failure=True,
                            terminal_failure_reason=reason, last_error=reason,
                            attitude_guard=dict(rejected=True, reason=reason)),
    )


def test_publication_record_preserves_general_readiness_when_height_guard_refuses_before_a_write():
    event = freshness_refusal_event()
    row = runner.publication_observation(event, general_connection_ready=True, timestamp=100., monotonic_s=10.)
    assert row["general_connection_ready"] is True
    assert row["final_guard_ready"] is False
    assert row["command_ready"] is False
    assert row["guard_refusal_reason"] == "altitude_sample_unavailable"
    assert row["attempted"] is False
    assert row["submitted_fields"] is None
    assert row["success"] is False
    assert row["fields"] == event["command_intent"].fields
    assert row["timestamp"] == 100.
    assert row["monotonic_s"] == 10.


@pytest.mark.parametrize("change", [
    {"publication_attempted": True}, {"publication_attempted": None}, {"submitted_fields": {}},
    {"last_publish_success": True}, {"terminal_failure": False},
    {"terminal_failure_reason": "different_failure"}, {"last_error": "rpc_failed"},
    {"guard": {"rejected": False, "reason": "altitude_sample_unavailable"}},
    {"guard": "unqualified_guard_metadata"},
    {"guard": {"rejected": True, "reason": "attitude_envelope_exceeded"},
     "terminal_failure_reason": "attitude_envelope_exceeded", "last_error": "attitude_envelope_exceeded"},
])
def test_publication_record_does_not_reclassify_actual_attempts_or_unverified_guard_refusals(change):
    event = freshness_refusal_event()
    for key, value in change.items():
        if key in {"publication_attempted", "submitted_fields"}:
            event[key] = value
        elif key == "guard":
            event["publish_status"]["attitude_guard"] = value
        else:
            event["publish_status"][key] = value
    row = runner.publication_observation(event, general_connection_ready=True)
    assert row["general_connection_ready"] is True
    assert row["command_ready"] is True
    assert row["final_guard_ready"] is None
    assert row["guard_refusal_reason"] is None
    assert row["attempted"] is event["publication_attempted"]
    assert row["submitted_fields"] == event["submitted_fields"]
    assert row["success"] is event["publish_status"]["last_publish_success"]


def test_publication_record_keeps_an_actual_failed_write_despite_stale_guard_details():
    event = freshness_refusal_event()
    event.update(publication_attempted=True, submitted_fields=dict(event["command_intent"].fields))
    row = runner.publication_observation(event, general_connection_ready=False)
    assert row["attempted"] is True
    assert row["success"] is False
    assert row["submitted_fields"] == event["submitted_fields"]
    assert row["final_guard_ready"] is None


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
        "GLOBAL_POSITION_INT": message(dict(type="GLOBAL_POSITION_INT", time_boot_ms=1000,
                                            relative_alt=20000, alt=520000)),
        "HOME_POSITION": message(dict(type="HOME_POSITION", altitude=500000)),
    }}}}}}
    manager = SimpleNamespace(current_altitude=20., get_flight_mode_text=lambda _: "Hold")
    flight = dict(fresh=True, flight_mode=1, arm_status="Armed", landed_state="MAV_LANDED_STATE_IN_AIR",
                  autopilot_uid="123456789")
    sample = runner.pose_observation(data, flight, manager, expected_aircraft_uid="123456789", monotonic_s=42.)
    assert sample["quaternion_wxyz"] == (1., 0., 0., 0.)
    assert sample["velocity_ned"] == (.1, .2, 0.)
    assert sample["position_ned"] == (1., 2., -20.)
    assert sample["altitude_m"] == 20.
    manager.current_altitude = None
    assert runner.pose_observation(data, flight, manager, expected_aircraft_uid="123456789")["altitude_m"] == 20.
    assert sample["source_boot_ms"] == (1000, 1005)
    assert sample["monotonic_s"] == 42.
    # Read-only post-Stop observation has no active following session to consult.
    assert runner.pose_observation(data, flight, manager, expected_aircraft_uid="123456789")["hold"]
    with pytest.raises(ValueError, match="UID mismatch"):
        runner.pose_observation(data, flight, manager, expected_aircraft_uid="987654321")


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
