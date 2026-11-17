"""Actual MC follower component qualification in an owned isolated SIH namespace.

The host launcher is shared infrastructure. This worker uses production target
dispatch, continuity, follower and MAVSDK publication, with simulated image or
boresight measurements. It does not qualify HTTP/App startup or camera selection.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from tools.fixed_camera_world_target import MCScenario, evaluate_response, stable_hold_window, mc_input_family
    from tools.sitl_gimbal_geometry_fixture import pose_from_mavlink2rest
except ModuleNotFoundError:
    from fixed_camera_world_target import MCScenario, evaluate_response, stable_hold_window, mc_input_family
    from sitl_gimbal_geometry_fixture import pose_from_mavlink2rest


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=lambda item: item.value) + "\n", encoding="utf-8")


def captured_response_scenario(validated, path):
    """Use owned runtime geometry/limits for analysis, not authored overrides.

    The input scenario has already passed MCScenario's no-override validation.
    The worker records resolved policy and actual airborne coordinates afterward;
    those observations must not be reparsed as operator configuration requests.
    """
    from classes.sih_visualization import VisualizationScenario
    captured = VisualizationScenario.from_yaml(path)
    if (not isinstance(validated, MCScenario)
            or (captured.follower_profile, captured.airframe, captured.mount_type, captured.altitude_control,
                captured.faults) != (validated.visual.follower_profile, validated.visual.airframe,
                validated.visual.mount_type, validated.visual.altitude_control, validated.visual.faults)):
        raise ValueError('captured_mc_response_contract_changed')
    return replace(validated, visual=captured)


def continuity_budget_snapshot(app):
    """Observe the sole supervisor's existing episode, without creating a clock."""
    owner = app._get_target_continuity_supervisor()
    return dict(loss_started_at_monotonic_s=owner._loss_started_at,
                loss_deadline_monotonic_s=owner._loss_deadline)


def _finite_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _retarget_budget_preserved(before, after, *, pending):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    keys = ('loss_started_at_monotonic_s', 'loss_deadline_monotonic_s')
    if set(before) != set(keys) or set(after) != set(keys):
        return False
    if not all(_finite_number(after[key]) for key in keys) or after[keys[1]] < after[keys[0]]:
        return False
    if not pending and all(before[key] is None for key in keys):
        return True
    return (all(_finite_number(before[key]) for key in keys)
            and before[keys[1]] >= before[keys[0]] and before == after)


def _bounded_gimbal_loss_exhausted(configured_policy, trackers, reason):
    """Match recorded production budget exhaustion to the captured policy."""
    if not isinstance(configured_policy, dict):
        return False
    try:
        policy = json.loads(json.dumps(configured_policy, default=lambda item: item.value))
    except (AttributeError, TypeError, ValueError):
        return False
    origin = policy.get('configuration_origin')
    if (policy.get('mode') != 'bounded_decay' or not isinstance(origin, str)
            or not (origin == 'configured_global' or origin.startswith('follower_override:'))
            or any(not _finite_number(policy.get(key)) or policy[key] <= 0.
                   for key in ('max_coast_time_s', 'max_coast_distance_m'))):
        return False
    for row in trackers:
        if not isinstance(row, dict):
            return False
        state = row.get('continuity') or {}
        if not isinstance(state, dict):
            return False
        request = state.get('handoff_request') or {}
        if not isinstance(request, dict):
            return False
        elapsed, distance = state.get('loss_elapsed_s'), state.get('coast_distance_m')
        if (state.get('authority_state') != 'HANDOFF_PENDING' or request.get('reason_code') != reason
                or state.get('reason_code') != reason
                or state.get('effective_policy') != policy
                or not _finite_number(elapsed) or elapsed < 0.
                or not _finite_number(distance) or distance < 0.):
            continue
        if ((reason == 'maximum_coast_time_reached' and elapsed >= policy['max_coast_time_s'])
                or (reason == 'maximum_coast_distance_reached' and distance >= policy['max_coast_distance_m']
                    and elapsed < policy['max_coast_time_s'])):
            return True
    return False


async def apply_simulated_retarget(app, *, family, coordinates, target_ned):
    """Exercise target-generation lifecycle, never physical ROI/API acceptance.

    Validate the received source before mutation. The dispatch watermark records
    this simulated selection event; only later received GAC/TRC can confirm it.
    No candidate angle observation is manufactured for request validation.
    """
    from classes.aircraft_state import finite_number
    if family not in {'image', 'angles'}:
        raise ValueError('sih_retarget_input_unsupported')
    if not isinstance(target_ned, (list, tuple)) or len(target_ned) != 3:
        raise ValueError('sih_retarget_target_invalid')
    target = tuple(finite_number(value, 'sih_retarget_target') for value in target_ned)
    if family == 'image' and coordinates is None:
        raise ValueError('Retarget candidate is outside the camera FOV; ownership remains unchanged')
    async with app._follower_state_lock:
        if getattr(app, '_camera_selection_pending', False):
            raise ValueError('sih_retarget_selection_pending')
        if not app._guidance_source_readiness(app.get_tracker_output())['ready']:
            raise ValueError('sih_retarget_source_unavailable')
        source = app._following_observation_source
        session = app._following_session_id
        before = app.get_target_continuity_status()
        before_budget = continuity_budget_snapshot(app)
        transition = app._prepare_following_target_transition('sih_simulated_target_retarget')
        if not transition.get('prepared'):
            raise ValueError('sih_retarget_preparation_refused')
        if family == 'angles':
            app._camera_selection_pending = True
        try:
            app._advance_tracking_session_generation(for_retarget=True)
            dispatched_epoch, dispatched_monotonic = time.time(), time.monotonic()
            if family == 'angles':
                app._camera_selection_dispatched_wall_time = dispatched_epoch
                app._camera_selection_dispatched_monotonic = dispatched_monotonic
        finally:
            if family == 'angles':
                app._camera_selection_pending = False
        after = app.get_target_continuity_status()
        after_budget = continuity_budget_snapshot(app)
        if (source != app._following_observation_source or session != app._following_session_id
                or not app._guidance_source_readiness(app.get_tracker_output())['ready']):
            raise ValueError('sih_retarget_source_changed')
        if before.get('target_transition_pending') and (
                after.get('episode_id') != before.get('episode_id')
                or after.get('coast_distance_m', 0.) < before.get('coast_distance_m', 0.)
                or after.get('loss_elapsed_s', 0.) < before.get('loss_elapsed_s', 0.)):
            raise ValueError('sih_retarget_renewed_recovery_budget')
        if family == 'angles' and not _retarget_budget_preserved(
                before_budget, after_budget, pending=before.get('target_transition_pending', False)):
            raise ValueError('sih_retarget_renewed_recovery_budget')
        return dict(event='retarget', before=before, after=after, target_ned=target,
            before_budget=before_budget, after_budget=after_budget,
            generation=app._tracking_session_generation, transition=transition,
            selection_kind='simulated_target_generation', physical_selection_api_qualified=False,
            dispatched_wall_time=dispatched_epoch, dispatched_monotonic_s=dispatched_monotonic)


@contextmanager
def observe_mode_calls(drone, record):
    """Observe action.hold/offboard.stop, including cleanup; no other SDK actions."""
    originals = []
    recording_errors = []
    def wrap(original, name):
        async def observed(*args, **kwargs):
            try:
                record(dict(method=name, monotonic_s=time.monotonic(), timestamp=time.time()))
            except Exception as exc:
                recording_errors.append(type(exc).__name__)
            return await original(*args, **kwargs)
        return observed
    try:
        for plugin, method, name in ((drone.action, 'hold', 'action.hold'),
                                     (drone.offboard, 'stop', 'offboard.stop')):
            original = getattr(plugin, method)
            originals.append((plugin, method, original))
            setattr(plugin, method, wrap(original, name))
        yield recording_errors
    finally:
        for plugin, method, original in reversed(originals):
            setattr(plugin, method, original)


def evaluate_fault_outcome(scenario, records, *, following_active, handoff,
                           retarget_count, takeover_requested_at, mode_calls,
                           telemetry_outage_injected, configured_policy=None, tracker_records=()):
    """Assess received evidence and pre-cleanup outcomes; own no recovery policy."""
    angles = mc_input_family(scenario.visual.follower_profile) == 'angles'
    def received_loss(row):
        if row.get('target_evidence_state') != 'ABSENT':
            return False
        return ((row.get('gimbal_observation') or {}).get('tracking_state') == 'TARGET_LOST'
                if angles else row.get('loss_active') is True)
    loss_seen = [row for row in records if received_loss(row)]
    checks = dict(expected_faults_executed=(
        all(any(start <= row['elapsed_s'] < end for row in loss_seen) for start, end in scenario.loss_windows)
        and bool(loss_seen) == bool(scenario.loss_windows)
        and (takeover_requested_at is not None) == (scenario.takeover_at_s is not None)
        and retarget_count == len(scenario.retargets)
        and telemetry_outage_injected == (scenario.telemetry_outage is not None)))
    reason = (handoff or {}).get('reason_code')
    if scenario.expected_handoff:
        expected_reasons = ({'maximum_coast_time_reached', 'maximum_coast_distance_reached'}
            if scenario.loss_windows and angles else {'maximum_coast_time_reached', 'maximum_coast_distance_reached',
                                                      'tracking_inactive', 'tracker_unusable_for_following'}
            if scenario.loss_windows else {'offboard_mode_exited'} if scenario.takeover_at_s is not None
            else {'vehicle_state_stale', 'follower_safety_rejected'})
        checks['fault_handoff_before_operator_cleanup'] = (
            following_active is False and bool(handoff) and reason in expected_reasons
            and handoff.get('result') in {'confirmed_hold', 'stopped'})
        if scenario.loss_windows and angles:
            checks['bounded_loss_budget_exhausted'] = _bounded_gimbal_loss_exhausted(
                configured_policy, tracker_records, reason)
    else:
        checks['following_active_until_operator_cleanup'] = following_active is True and not handoff
    if scenario.loss_windows and not scenario.expected_handoff:
        recovered = []
        windows = sorted(scenario.loss_windows)
        for index, (_start, end) in enumerate(windows):
            next_start = windows[index + 1][0] if index + 1 < len(windows) else scenario.duration_s
            healthy = [row for row in records if end <= row['elapsed_s'] < next_start
                       and row.get('target_evidence_state') == 'CONFIRMED'
                       and (not angles or (row.get('gimbal_observation') or {}).get('tracking_state') == 'TRACKING_ACTIVE')]
            states = [(row.get('continuity') or {}).get('authority_state') for row in healthy]
            recovered.append('REACQUIRING' in states and 'ACTIVE' in states
                             and states.index('REACQUIRING') < states.index('ACTIVE'))
        checks['received_loss_reacquired_and_restored'] = all(recovered)
    if scenario.retargets:
        checks['replacement_target_restored'] = any(
            row['elapsed_s'] >= scenario.retargets[-1][0]
            and (row.get('continuity') or {}).get('reason_code') == 'target_authority_restored'
            for row in records)
    if scenario.takeover_at_s is not None:
        calls = [row['method'] for row in mode_calls
                 if takeover_requested_at is not None and row['monotonic_s'] >= takeover_requested_at]
        # The observer covers these two mode-writing SDK methods, including
        # final manager cleanup; it does not audit unrelated actions such as Land.
        checks['takeover_no_backend_hold_or_offboard_stop'] = calls == ['action.hold']
    return checks


def validate_retained_fault_outcome(scenario, result, evidence, *, expected_handoff,
                                    fault_events, takeover_cleanup=None, pre_cleanup=None, mode_calls=None):
    """Check captured witnesses without requiring new fields on legacy evidence."""
    if not scenario.faults:
        return
    kinds = {fault['kind'] for fault in scenario.faults}
    handoff = result.get('handoff') or {}
    reason = handoff.get('reason_code')
    trackers = evidence['tracker']
    states = sorted([*evidence['state'], *trackers], key=lambda row: row['timestamp'])
    def refused():
        raise ValueError('captured_mc_fault_outcome_unproven')
    if type(expected_handoff) is not bool or (pre_cleanup is not None and (
            not isinstance(pre_cleanup.get('checks'), dict)
            or not pre_cleanup['checks'] or any(value is not True for value in pre_cleanup['checks'].values()))):
        refused()
    if expected_handoff:
        reasons = ({'tracker_unusable_for_following', 'tracking_inactive',
                    'maximum_coast_time_reached', 'maximum_coast_distance_reached'} if kinds == {'target_loss'}
                   else {'offboard_mode_exited'} if kinds == {'pilot_takeover'}
                   else {'vehicle_state_stale', 'follower_safety_rejected'} if kinds == {'stale_telemetry'} else set())
        if reason not in reasons or handoff.get('result') not in {'confirmed_hold', 'stopped'}:
            refused()
        if pre_cleanup is not None and (pre_cleanup.get('following_active') is not False
                or (pre_cleanup.get('handoff') or {}).get('reason_code') != reason):
            refused()
    elif reason != 'operator_stop':
        refused()
    if kinds == {'target_loss'}:
        angles = mc_input_family(scenario.follower_profile) == 'angles'
        def lost(row):
            output = row.get('tracker_output') or {}
            if output.get('tracking_active') is not False or output.get('usable_for_following') is not False:
                return False
            return ((output.get('gimbal_observation') or {}).get('tracking_state') == 'TARGET_LOST'
                    if angles else output.get('has_output') is False)
        losses = [row for row in trackers if lost(row)]
        if not losses:
            refused()
        if expected_handoff:
            if not any(((row.get('continuity') or {}).get('handoff_request') or {}).get('reason_code') == reason
                       for row in trackers):
                refused()
            if angles:
                policy = (pre_cleanup or {}).get('configured_continuity_policy')
                if (result.get('configured_continuity_policy') != policy
                        or not _bounded_gimbal_loss_exhausted(policy, trackers, reason)):
                    refused()
        else:
            after_loss = [row for row in states if row['timestamp'] > losses[0]['timestamp']]
            reacquiring = [row['timestamp'] for row in after_loss
                if (row.get('continuity') or row).get('authority_state') == 'REACQUIRING']
            if not reacquiring or not any(row['timestamp'] > reacquiring[0]
                    and (row.get('continuity') or row).get('reason_code') == 'target_authority_restored'
                    for row in after_loss):
                refused()
    elif kinds == {'pilot_takeover'}:
        events = [row for row in fault_events if row.get('event') == 'pilot_takeover' and row.get('mode') == 'Hold']
        cleanup = takeover_cleanup or {}
        quiesce = cleanup.get('sender_quiesce') or {}
        if (not events or cleanup.get('errors') or quiesce.get('authority_released') is not True
                or quiesce.get('local_sender_quiesced') is not True
                or quiesce.get('vehicle_hold_acknowledged') is not False or 'offboard_stop_action' in cleanup):
            refused()
        if mode_calls is not None and [row['method'] for row in mode_calls
                if row['timestamp'] >= events[0]['timestamp']] != ['action.hold']:
            refused()
    elif kinds == {'stale_telemetry'}:
        if (not any(row.get('event') == 'stale_telemetry' for row in fault_events)
                or not any(row.get('dispatch_accepted') is False for row in trackers)):
            refused()
    elif kinds == {'retarget'}:
        events = [row for row in fault_events if row.get('event') == 'retarget']
        if len(events) != len(scenario.faults) or not any(
                (row.get('continuity') or row).get('reason_code') == 'target_authority_restored' for row in states):
            refused()
        for event in events:
            before, after = event.get('before') or {}, event.get('after') or {}
            if before.get('target_transition_pending') and (
                    after.get('episode_id') != before.get('episode_id')
                    or after.get('coast_distance_m', 0.) < before.get('coast_distance_m', 0.)
                    or after.get('loss_elapsed_s', 0.) < before.get('loss_elapsed_s', 0.)):
                refused()
            if mc_input_family(scenario.follower_profile) == 'angles' and not _retarget_budget_preserved(
                    event.get('before_budget'), event.get('after_budget'),
                    pending=before.get('target_transition_pending', False)):
                refused()
        if mc_input_family(scenario.follower_profile) == 'angles' and not any(
                row['timestamp'] > max(event['timestamp'] for event in events)
                and (row.get('continuity') or row).get('reason_code') == 'target_authority_restored'
                for row in states):
            refused()
    else:
        refused()


def request_telemetry_identity(http):
    """Request the simulator's own identity on its independent telemetry route."""
    endpoint = "http://127.0.0.1:8088"
    response = http.get(endpoint + "/v1/helper/mavlink?name=COMMAND_LONG", timeout=2)
    response.raise_for_status()
    packet = response.json()
    packet["message"].update(
        param1=148.0, command={"type": "MAV_CMD_REQUEST_MESSAGE"},
        target_system=1, target_component=1,
    )
    http.post(endpoint + "/v1/mavlink", json=packet, timeout=2).raise_for_status()


def run_host(args, scenario_path):
    """Stage only qualification inputs; public and operator configuration stay untouched."""
    from tools.sih_isolated_host import host

    scenario_path = scenario_path.resolve()
    scenario = MCScenario.from_yaml(scenario_path)
    if args.enable_altitude_control:
        scenario = replace(scenario, visual=replace(scenario.visual, altitude_control=True))
    if args.backend_repo.resolve() != ROOT:
        raise ValueError("MC qualification must capture this runner's own backend checkout")
    args.output = args.evidence_root
    args.mount = scenario.visual.mount_type
    args.simulator_model = "sihsim_quadx"
    args.evidence_kind = "mc-world-target-component"
    args.worker_extra_args = []

    def configure(config):
        stage = args.output.resolve()
        for name in ("fixed_camera_world_target.py", "mc_follower_sih.py", "sih_gimbal_world_target.py"):
            shutil.copyfile(ROOT / "tools" / name, stage / "backend/tools" / name)
        import yaml
        staged_scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        staged_scenario["follower"]["altitude_control"] = scenario.visual.altitude_control
        family = mc_input_family(args.follower)
        config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] = 'Gimbal' if family == 'angles' else 'CSRT'
        telemetry_source = getattr(args, "telemetry_source", "mavlink2rest")
        if telemetry_source not in {"mavlink2rest", "mavsdk"}:
            raise ValueError("Unsupported MC control telemetry source")
        config["Follower"]["USE_MAVLINK2REST"] = telemetry_source == "mavlink2rest"
        from classes.follower_catalog import get_follower_profile
        section = get_follower_profile(args.follower).config_section
        config["Follower"]["FollowerOverrides"].setdefault(section, {})[
            "ENABLE_ALTITUDE_CONTROL"
        ] = scenario.visual.altitude_control
        if family == 'angles':
            config['GimbalTracker'].update(MOUNT_TYPE=args.mount, ENABLED=True, CONTROL_ENABLED=False)
            config['Follower']['FollowerOverrides'][section]['LATERAL_GUIDANCE_MODE'] = scenario.visual.lateral_guidance_mode
        if args.follower == "mc_velocity_ground":
            config["MC_VELOCITY_GROUND"]["ENABLE_DESCEND_TO_TARGET"] = scenario.visual.altitude_control
        # Direct-rate altitude/thrust settings remain their declared saved values.
        limits = {**config["Safety"]["GlobalLimits"],
                  **config["Safety"]["FollowerOverrides"].get(section, {})}
        staged_scenario["constraints"] = {
            "velocity": {"forward": limits["MAX_VELOCITY_FORWARD"], "right": limits["MAX_VELOCITY_LATERAL"],
                         "down": limits["MAX_VELOCITY_VERTICAL"] if scenario.visual.altitude_control else 0.},
            "rate": {"yaw": limits["MAX_YAW_RATE"]},
            "altitude": {"min": limits["MIN_ALTITUDE"], "max": limits["MAX_ALTITUDE"]},
        }
        initial_altitude = -staged_scenario["initial_conditions"]["vehicle_ned"][2]
        if (initial_altitude < limits["MIN_ALTITUDE"]
                or limits["MAX_ALTITUDE"] is not None and initial_altitude > limits["MAX_ALTITUDE"]):
            raise ValueError("Scenario airborne start is outside the configured altitude envelope; "
                             "choose valid initial_conditions without reducing saved safety limits")
        staged_scenario["continuity_policy"] = {"mode": config["TargetContinuity"]["MODE"]}
        (stage / "scenario.yaml").write_text(yaml.safe_dump(staged_scenario, sort_keys=False))
        write_json(stage / "harness-inputs.json", {
            "scenario_sha256": hashlib.sha256((stage / "scenario.yaml").read_bytes()).hexdigest(),
            "source_scenario_sha256": hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
            "qualification_scope": "MC component with simulated boresight" if family == 'angles' else "MC component with simulated fixed-camera measurements",
            "control_telemetry_source": telemetry_source,
            "camera_projection": asdict(scenario.camera) if scenario.camera is not None else None,
            "fixture_kind": 'simulated_boresight' if family == 'angles' else 'simulated_fixed_camera_projection',
            "synthetic_image_size_px": None if family == 'angles' else [640, 480],
            "image_normalization": None if family == 'angles' else 'legacy_dimension_half',
            "tools": {name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest()
                      for name in ("fixed_camera_world_target.py", "mc_follower_sih.py", "sih_gimbal_world_target.py", "sih_isolated_host.py")},
            "safety_policy": "checked-in defaults, no scenario limit or PID-gain adoption",
            "measurement_timing": "REST source receipt approximation; sensor capture time is unavailable",
        })

    host(args, driver_path=Path(__file__), configure=configure)


def pose_observation(payload, flight_state, manager, *, expected_aircraft_uid, monotonic_s=None):
    """Read raw physical quaternion, independent NED motion and source progress."""
    from classes.aircraft_state import Quaternion

    if (not isinstance(expected_aircraft_uid, str) or not expected_aircraft_uid
            or flight_state.get("autopilot_uid") != expected_aircraft_uid):
        raise ValueError("MAVSDK/REST aircraft UID mismatch")
    position, quaternion = pose_from_mavlink2rest(payload, 1)
    messages = payload["vehicles"]["1"]["components"]["1"]["messages"]
    local = messages["LOCAL_POSITION_NED"]["message"]
    attitude = messages["ATTITUDE_QUATERNION"]["message"]
    velocity = tuple(float(local[key]) for key in ("vx", "vy", "vz"))
    if not all(math.isfinite(value) for value in velocity):
        raise ValueError("Non-finite independently observed velocity")
    q = Quaternion(*quaternion)
    roll = math.atan2(2 * (q.w * q.x + q.y * q.z), 1 - 2 * (q.x * q.x + q.y * q.y))
    pitch = math.asin(max(-1., min(1., 2 * (q.w * q.y - q.z * q.x))))
    global_position = messages["GLOBAL_POSITION_INT"]["message"]
    home = messages["HOME_POSITION"]["message"]
    relative_mm, absolute_mm, home_mm = (global_position["relative_alt"], global_position["alt"], home["altitude"])
    if (any(type(value) is not int for value in (relative_mm, absolute_mm, home_mm))
            or abs(absolute_mm - relative_mm - home_mm) > 2):
        raise ValueError("Independent relative altitude/home reference unavailable")
    altitude = relative_mm / 1000.
    if not flight_state.get("fresh"):
        raise ValueError("Flight state is not fresh")
    mode_text = None if manager is None else manager.get_flight_mode_text(flight_state.get("flight_mode"))
    return dict(
        monotonic_s=time.monotonic() if monotonic_s is None else monotonic_s,
        position_ned=position, quaternion_wxyz=quaternion, velocity_ned=velocity,
        altitude_m=altitude, roll_deg=math.degrees(roll), pitch_deg=math.degrees(pitch),
        yaw_rad=q.heading_rad,
        source_boot_ms=(int(local["time_boot_ms"]), int(attitude["time_boot_ms"])),
        source_receipt_times={name: messages[name]["status"]["time"]["last_update"]
                              for name in ("LOCAL_POSITION_NED", "ATTITUDE_QUATERNION")},
        source="px4_mavlink2rest_observed",
        flight_mode=flight_state.get("flight_mode"),
        hold=None if mode_text is None else mode_text == "Hold",
        airborne=(flight_state.get("arm_status") == "Armed"
                  and flight_state.get("landed_state") == "MAV_LANDED_STATE_IN_AIR"),
    )


def tracker_observation(coordinates, *, measurement_epoch_s, measurement_monotonic_s, lost=False, target_id=0):
    """A missing target has no fabricated image coordinate or measurement time."""
    from classes.tracker_output import TrackerDataType, TrackerOutput

    visible = coordinates is not None and not lost
    raw = dict(has_output=visible, usable_for_following=visible, data_is_stale=False,
               identity_confirmed=visible, source="simulated_fixed_camera")
    if visible:
        raw.update(measurement_epoch_s=measurement_epoch_s,
                   measurement_monotonic_s=measurement_monotonic_s,
                   measurement_time_basis="pose_receipt_time_approximation")
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D, timestamp=measurement_epoch_s,
        tracking_active=visible, tracker_id="fixed_camera_world_fixture",
        position_2d=coordinates if visible else None, target_id=target_id if visible else None,
        confidence=1. if visible else None, raw_data=raw,
    )


def bind_projected_image(app, observation, sample, target):
    """Attach a declared synthetic grid to an actual source-owned projected sample."""
    from classes.frame_publisher import CaptureStamp
    from classes.guidance_observation import ImageFrameContext, ObservationProvenance

    width, height = 640, 480
    capture = CaptureStamp(app.frame_publisher.control_source_epoch, ':'.join(map(str, sample['source_boot_ms'])),
                           sample['monotonic_s'], 'fresh')
    context = ImageFrameContext(ObservationProvenance(app.frame_publisher.stream_id,
        app._tracking_session_generation, 'sih-projected-grid-640x480-v2', None, capture), (width, height))
    if observation.position_2d is not None:
        x, y = observation.position_2d
        # Invert BaseTracker's legacy dimension/2 normalization. Typed pixels
        # still require actual centres in [0, dimension-1]; never clamp an edge.
        observation.image_measurement = context.at_pixel(((x + 1.) * width / 2., (y + 1.) * height / 2.))
    app.tracking_input_context = context
    observation.raw_data.update(fixture_kind='simulated_fixed_camera_projection', measurement_target_ned=tuple(target))
    app._sih_tracker_output = observation
    return observation


def observed_command_release(sample, publisher_status, timestamp, released_at=None):
    """Read-only proof of Hold with no live publication task; never infer from a gap."""
    if (sample.get("hold") is not True or publisher_status.get("running") is not False
            or publisher_status.get("task_active") is not False):
        return None
    return dict(
        timestamp=timestamp, state="INACTIVE", authority_state="INACTIVE", command_expected=False,
        observed_hold=True, publisher_running=False, publisher_task_active=False,
        command_owner_released_at=timestamp if released_at is None else released_at,
        reason_code="observed_hold_after_local_publication_stop", events=["Hold"],
    )


def publication_observation(event, *, general_connection_ready, timestamp=None, monotonic_s=None):
    """Keep actual writes distinct from a production freshness-guard refusal."""
    status = event["publish_status"]
    guard = status.get("attitude_guard")
    guard = guard if isinstance(guard, dict) else {}
    reason = guard.get("reason")
    freshness_refusal = (
        event.get("publication_attempted") is False and event.get("submitted_fields") is None
        and status.get("last_publish_success") is False and guard.get("rejected") is True
        and reason in {"altitude_sample_unavailable", "attitude_sample_unavailable", "attitude_sample_stale"}
        and status.get("terminal_failure") is True
        and status.get("terminal_failure_reason") == reason and status.get("last_error") == reason
    )
    intent = event.get("command_intent")
    return dict(
        timestamp=time.time() if timestamp is None else timestamp,
        monotonic_s=time.monotonic() if monotonic_s is None else monotonic_s,
        success=status["last_publish_success"] is True,
        fields=event.get("submitted_fields") if intent is None else dict(intent.fields),
        submitted_fields=event.get("submitted_fields"), attempted=event.get("publication_attempted"),
        general_connection_ready=general_connection_ready,
        final_guard_ready=False if freshness_refusal else None,
        guard_refusal_reason=reason if freshness_refusal else None,
        command_ready=False if freshness_refusal else general_connection_ready,
    )


class PoseProgress:
    """Cached REST polls do not create a measurement or renew source freshness."""

    def __init__(self, timeout_s=.5):
        self.previous = None
        self.latest_seen = None
        self.last_progress_at = None
        self.timeout_s = timeout_s

    def accept(self, source_boot_ms, now):
        if self.previous is not None:
            if any(current < previous for current, previous in zip(source_boot_ms, self.latest_seen)):
                raise RuntimeError("PX4 pose source time moved backward")
            self.latest_seen = source_boot_ms
            if any(current == previous for current, previous in zip(source_boot_ms, self.previous)):
                if now - self.last_progress_at > self.timeout_s:
                    raise RuntimeError("PX4 pose progress expired; polling cannot refresh evidence")
                return False
        self.previous = source_boot_ms
        self.latest_seen = source_boot_ms
        self.last_progress_at = now
        return True


async def worker(args):
    if not os.environ.get("EVIDENCE_OWNER") or set(os.listdir("/sys/class/net")) != {"lo"}:
        raise RuntimeError("MC worker requires the owned loopback-only Docker namespace")
    import requests
    import yaml
    from classes.app_controller import AppController
    from classes.command_intent import CommandIntent
    from classes.follower import Follower
    from classes.mavlink_data_manager import MavlinkDataManager
    from classes.offboard_commander import OffboardCommander
    from classes.parameters import Parameters
    from classes.px4_interface_manager import PX4InterfaceManager, _evaluate_px4_command_gate
    from classes.target_continuity import ContinuityPolicy, TargetContinuitySupervisor
    from classes.tracker_trace import TrackerTraceRecorder

    output = Path("/work/evidence")
    manifest = json.loads((output / "manifest.json").read_text())
    config_bytes = (output / "configs/config.yaml").read_bytes()
    if (manifest.get("network") != "none" or manifest.get("host_ports") != []
            or manifest.get("simulator_model") != "sihsim_quadx"
            or hashlib.sha256(config_bytes).hexdigest() != manifest["config_sha256"]):
        raise RuntimeError("Staged simulator isolation/configuration identity mismatch")
    scenario = MCScenario.from_yaml(output / "scenario.yaml")
    if scenario.visual.follower_profile != args.follower or Parameters.FOLLOWER_MODE != args.follower:
        raise RuntimeError("Selected profile differs from the staged scenario")
    if mc_input_family(args.follower) == 'angles' and (
            manifest.get('sih_baseline', {}).get('kind') != 'verified_source_build'
            or manifest.get('mount') != scenario.visual.mount_type or args.mount != scenario.visual.mount_type):
        raise RuntimeError('Gimbal MC renewal requires matching source-attested build and mount')
    config = yaml.safe_load(config_bytes)
    if (config["PX4"]["SYSTEM_ADDRESS"] != "udpin://127.0.0.1:14540"
            or config["PX4"]["MAVSDK_SERVER_ADDRESS"] != "127.0.0.1"
            or config["MAVLink"]["MAVLINK_HOST"] != "127.0.0.1"):
        raise RuntimeError("MC worker refuses non-loopback flight endpoints")
    app = AppController.__new__(AppController)
    app.bind_flight_event_loop(asyncio.get_running_loop())
    app.mavlink_data_manager = MavlinkDataManager(
        Parameters.MAVLINK_HOST, Parameters.MAVLINK_PORT,
        Parameters.MAVLINK_POLLING_INTERVAL, Parameters.MAVLINK_DATA_POINTS, enabled=True,
    )
    observer = MavlinkDataManager(
        Parameters.MAVLINK_HOST, Parameters.MAVLINK_PORT,
        Parameters.MAVLINK_POLLING_INTERVAL, Parameters.MAVLINK_DATA_POINTS, enabled=True,
    )
    manager = PX4InterfaceManager(app)
    app.px4_interface = app._active_following_controller = manager
    app._follower_state_lock = asyncio.Lock()
    app._tracker_model_state_lock = threading.RLock()
    app._tracking_session_generation = 0
    app.following_execution_mode = "PX4"
    app.following_active = False
    app.estimator = None
    app.telemetry_handler = SimpleNamespace(follower=None)
    app._following_session_id = None
    app._following_stopping = False
    app.mavlink_data_manager.register_offboard_exit_callback(app._schedule_offboard_mode_exit)
    app.camera_runtime = SimpleNamespace(provider=None)
    family = mc_input_family(args.follower)
    progress_guard = PoseProgress()
    gimbal_source = None
    if family == 'angles':
        try:
            from tools.sih_gimbal_world_target import SihGimbalWorldTarget
        except ModuleNotFoundError:
            from sih_gimbal_world_target import SihGimbalWorldTarget
        gimbal_source = SihGimbalWorldTarget(app, progress=progress_guard)
    else:
        from classes.frame_publisher import FramePublisher
        app.frame_publisher = FramePublisher()
        app.frame_publisher.stream_id = 'sih-projected-image:' + app.frame_publisher.stream_id
        app.frame_publisher.invalidate_source('sih-pose-source:' + uuid.uuid4().hex)
        app.current_tracker_type = 'CSRT'
        app._sih_tracker_output = None
        app.get_tracker_output = lambda: app._sih_tracker_output
    app._get_video_frame_status_for_following = lambda: dict(
        source='none' if family == 'angles' else 'simulated_fixed_camera',
        usable_for_following=family == 'image', replay_source=False,
    )
    app.target_continuity = TargetContinuitySupervisor(
        ContinuityPolicy.resolve(Parameters.TargetContinuity, args.follower)
    )
    app.target_continuity.reset_session(session_epoch=0, reason="mc_world_target_sih")
    app.tracker_trace_recorder = TrackerTraceRecorder(
        tracker_command_trace_path=output / "trace/tracker_command_trace.jsonl",
        offboard_publish_trace_path=output / "trace/offboard_publish_trace.jsonl",
        source="mc_world_target_sih",
    )
    records, publications, mode_calls = [], [], []
    mode_observer = ExitStack()
    report = None
    armed = False

    def log(name, row):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")

    def publication(event):
        app._record_offboard_publish_result(event)
        publications.append(publication_observation(event,
            general_connection_ready=manager.is_command_connection_ready(require_fresh_telemetry=True)))

    async def snapshot():
        payload = await asyncio.to_thread(
            lambda: requests.get("http://127.0.0.1:8088/v1/mavlink", timeout=2).json()
        )
        flight = observer.get_flight_state()
        sample = pose_observation(
            payload, flight, manager, expected_aircraft_uid=identity["autopilot_uid"],
        )
        log("raw-pose-observations.jsonl", dict(timestamp=time.time(), **sample))
        return sample

    def produce(sample, target, *, lost=False):
        epoch = time.time()
        if gimbal_source is not None:
            return gimbal_source.observe(sample, target, epoch_s=epoch, lost=lost)
        if not progress_guard.accept(sample['source_boot_ms'], time.monotonic()):
            return None
        coordinates = scenario.camera.project(sample['position_ned'], sample['quaternion_wxyz'], target)
        if coordinates is None and not lost:
            raise RuntimeError('Independent world target left the declared fixed-camera FOV')
        observation = tracker_observation(coordinates, measurement_epoch_s=epoch,
            measurement_monotonic_s=sample['monotonic_s'], lost=lost, target_id=app._tracking_session_generation)
        return bind_projected_image(app, observation, sample, target)

    async def wait_for(predicate, timeout=60.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            await asyncio.sleep(.1)
        raise RuntimeError("Simulated aircraft readiness deadline expired")

    def retain_pose(sample, timestamp):
        log("px4/pose_trace.jsonl", dict(timestamp=timestamp, vehicle_ned=sample["position_ned"],
            vehicle_quaternion=sample["quaternion_wxyz"], source=sample["source"],
            source_boot_ms=sample["source_boot_ms"]))

    async def observe_handoff(operation):
        """Keep actual pose evidence flowing while awaiting control-owner cleanup."""
        task = asyncio.create_task(operation)
        released_at = None
        try:
            while not task.done():
                sample = await snapshot()
                epoch = time.time()
                retain_pose(sample, epoch)
                release = observed_command_release(sample, commander.get_status(), epoch, released_at)
                if release is not None:
                    released_at = release["command_owner_released_at"]
                    log("trace/follower_state.jsonl", release)
                target = scenario.target_at(min(time.monotonic() - started, scenario.duration_s), anchor)
                log("trace/target_truth.jsonl", dict(timestamp=epoch, target_ned=target))
                await asyncio.sleep(1. / scenario.visual.rate_hz)
            return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    try:
        app.mavlink_data_manager.start_polling()
        observer.start_polling()
        await manager.connect()
        def record_mode_call(row):
            mode_calls.append(row)
            log('sdk-mode-calls.jsonl', row)
        mode_recording_errors = mode_observer.enter_context(observe_mode_calls(manager.drone, record_mode_call))
        await wait_for(lambda: manager.is_command_connection_ready(require_fresh_telemetry=True))
        await manager.observe_aircraft_identity()
        identity = manager.get_aircraft_identity()
        if not identity.get("autopilot_uid"):
            raise RuntimeError("Simulated aircraft UID unavailable")
        app._following_session_aircraft_uid = identity["autopilot_uid"]
        app._following_session_connection_generation = identity["connection_generation"]
        write_json(output / "identity.json", identity)
        await asyncio.to_thread(request_telemetry_identity, requests)
        await wait_for(lambda: app.mavlink_data_manager.get_flight_state().get("fresh") is True)
        telemetry_identity = app.mavlink_data_manager.get_aircraft_identity()
        write_json(output / "telemetry-identity.json", telemetry_identity)
        if telemetry_identity.get("autopilot_uid") != identity["autopilot_uid"]:
            raise RuntimeError("Independent telemetry/command identities disagree")
        await wait_for(lambda: observer.get_flight_state().get("fresh") is True)
        if observer.get_aircraft_identity().get("autopilot_uid") != identity["autopilot_uid"]:
            raise RuntimeError("Read-only observer aircraft UID disagrees")
        write_json(output / "observer-identity.json", observer.get_aircraft_identity())
        Parameters.FOLLOWER_CIRCUIT_BREAKER = False
        async def armable():
            async for health in manager.drone.telemetry.health():
                if health.is_armable:
                    return
        await asyncio.wait_for(armable(), timeout=45)
        altitude = -scenario.visual.initial_vehicle_ned[2]
        if not 5. <= altitude <= 50.:
            raise ValueError("Simulated takeoff altitude must be in [5, 50] m")
        await manager.drone.action.set_takeoff_altitude(altitude)
        await manager.drone.action.arm()
        armed = True
        await manager.drone.action.takeoff()
        await wait_for(lambda: manager.current_altitude is not None and manager.current_altitude > altitude - 1.)
        await manager.drone.action.hold()
        window = []
        deadline = time.monotonic() + 75.
        while time.monotonic() < deadline:
            sample = await snapshot()
            window = [*window[-6:], sample]
            if stable_hold_window(window, expected_altitude_m=altitude):
                break
            await asyncio.sleep(.5)
        else:
            raise RuntimeError("Seven fresh stable airborne Hold samples were not observed")
        write_json(output / "stable-flight.json", window)
        anchor = tuple(sample["position_ned"][i] - scenario.visual.initial_vehicle_ned[i] for i in range(3))
        write_json(output / "frozen-target-anchor.json", dict(anchor_ned=anchor, observation=sample))
        app.follower = Follower(manager, (0., 0.))
        concrete = app.follower.follower
        concrete.reset_control_session()
        if app.follower.get_airframe_phase() != "multicopter":
            raise RuntimeError("MC follower phase contract mismatch")
        initial_target = scenario.target_at(0., anchor)
        if scenario.camera is not None and scenario.camera.project(sample["position_ned"], sample["quaternion_wxyz"], initial_target) is None:
            raise RuntimeError("Frozen world target is not visible from the actual settled aircraft pose")
        if produce(sample, initial_target) is None:
            raise RuntimeError('Initial independent projection did not progress')
        start_input_identity = app._freeze_following_observation_source()
        executed = yaml.safe_load((output / "scenario.yaml").read_text())
        executed["evidence_provenance"] = "px4_sih"
        executed["initial_conditions"]["vehicle_ned"] = list(sample["position_ned"])
        executed["initial_conditions"]["quaternion_wxyz"] = list(sample["quaternion_wxyz"])
        for waypoint in executed["target"]["waypoints"]:
            waypoint["position_ned"] = [waypoint["position_ned"][i] + anchor[i] for i in range(3)]
        executed["constraints"] = {
            "velocity": {"forward": concrete.velocity_limits.forward, "right": concrete.velocity_limits.lateral,
                         "down": concrete.velocity_limits.vertical if scenario.visual.altitude_control else 0.},
            "rate": {"yaw": math.degrees(concrete.rate_limits.yaw)},
            "altitude": {"min": concrete.altitude_limits.min_altitude, "max": concrete.altitude_limits.max_altitude},
        }
        resolved_policy = asdict(ContinuityPolicy.resolve(Parameters.TargetContinuity, args.follower))
        executed["continuity_policy"] = {"mode": resolved_policy["mode"].value}
        executed["resolved_runtime_policy"] = json.loads(json.dumps(resolved_policy, default=lambda item: item.value))
        executed["frozen_target_anchor_ned"] = list(anchor)
        (output / "scenario.yaml").write_text(yaml.safe_dump(executed, sort_keys=False))
        response_scenario = captured_response_scenario(scenario, output / "scenario.yaml")
        write_json(output / "runtime-policy.json", dict(continuity=resolved_policy,
            velocity=concrete.velocity_limits._asdict(), altitude=concrete.altitude_limits._asdict(),
            rates_rad_s=concrete.rate_limits._asdict(), pid_gains=config["PID"]["PID_GAINS"]))
        commander = OffboardCommander(manager, concrete.setpoint_handler, on_publish_result=publication,
            before_dispatch=app._command_dispatch_guard(), stop_before_dispatch=app._command_dispatch_guard(teardown=True),
            dispatch_context=app._command_dispatch_context())
        app.offboard_commander = commander
        app._require_follow_start_input_identity(start_input_identity, {}, stage='sih_before_offboard')
        start_task = asyncio.create_task(manager.start_offboard_mode(
            before_dispatch=app._command_dispatch_guard(),
            on_mode_dispatch=lambda: write_json(output / 'mode-dispatch.json',
                                               dict(observed_at_monotonic_s=time.monotonic()))))
        try:
            # Real startup primes for >1 s; keep the same read-only source progressing.
            while not start_task.done():
                initial_sample = await snapshot()
                produce(initial_sample, initial_target)
                retain_pose(initial_sample, time.time())
                log('trace/target_truth.jsonl', dict(timestamp=time.time(), target_ned=initial_target))
                log('trace/follower_state.jsonl', dict(timestamp=time.time(), state='INACTIVE',
                    authority_state='INACTIVE', command_expected=False, reason_code='guidance_publication_not_started'))
                await asyncio.sleep(1. / scenario.visual.rate_hz)
            start_result = await start_task
        finally:
            if not start_task.done():
                start_task.cancel()
                await asyncio.gather(start_task, return_exceptions=True)
        app._require_follow_start_input_identity(start_input_identity, {}, stage='sih_after_offboard')
        if not start_result.get("executed"):
            raise RuntimeError("Production Offboard start failed")
        seed = CommandIntent(args.follower, app.follower.get_control_type(),
                             concrete.setpoint_handler.get_fields(), "isolated_sih_baseline")
        if not app._submit_command_intent_to_commander(seed):
            raise RuntimeError("Initial complete safe command was refused")
        await commander.start()
        app.following_active = True
        started = time.monotonic()
        takeover_requested_at = None
        takeover_cleanup = None
        retarget_count = 0
        telemetry_outage_injected = False
        telemetry_outage_started_at = None
        while time.monotonic() - started < scenario.duration_s and app.following_active:
            sample = await snapshot()
            elapsed = time.monotonic() - started
            if (scenario.telemetry_outage is not None and not telemetry_outage_injected
                    and elapsed >= scenario.telemetry_outage[0]):
                app.mavlink_data_manager.inject_timeout_for_validation(
                    timeout_window_s=scenario.telemetry_outage[1], force_stale=True,
                    reason="sih_control_telemetry_outage",
                )
                telemetry_outage_injected = True
                telemetry_outage_started_at = time.monotonic()
                log("fault-events.jsonl", dict(timestamp=time.time(), event="stale_telemetry",
                    duration_s=scenario.telemetry_outage[1], observer="separate unaffected read-only client"))
            if scenario.takeover_at_s is not None and elapsed >= scenario.takeover_at_s:
                # A separate simulator pilot changes PX4 mode. The backend must
                # observe that change and release its owner without another Hold.
                takeover_requested_at = time.monotonic()
                log("fault-events.jsonl", dict(timestamp=time.time(), event="pilot_takeover", mode="Hold"))
                async def pilot_takeover():
                    await manager.drone.action.hold()
                    await wait_for(lambda: not app.following_active, timeout=manager.get_mavsdk_command_timeout_s())
                    cleanup = getattr(app, "_following_stop_future", None)
                    return await asyncio.shield(cleanup) if cleanup is not None else None
                takeover_cleanup = await observe_handoff(pilot_takeover())
                break
            target = scenario.target_at(elapsed, anchor)
            if target is None:
                break
            log("trace/target_truth.jsonl", dict(timestamp=time.time(), target_ned=target))
            coordinates = (scenario.camera.project(sample["position_ned"], sample["quaternion_wxyz"], target)
                           if scenario.camera is not None else None)
            due = sum(at <= elapsed for at, _offset in scenario.retargets)
            while retarget_count < due:
                candidate = scenario.target_at(scenario.retargets[retarget_count][0], anchor)
                candidate_coordinates = (scenario.camera.project(sample['position_ned'], sample['quaternion_wxyz'], candidate)
                                         if scenario.camera is not None else None)
                event = await apply_simulated_retarget(app, family=family,
                    coordinates=candidate_coordinates, target_ned=candidate)
                log('fault-events.jsonl', dict(timestamp=time.time(), **event))
                retarget_count += 1
            lost = any(start <= elapsed < end for start, end in scenario.loss_windows)
            observation = produce(sample, target, lost=lost)
            if observation is None:
                log('skipped-pose-polls.jsonl', dict(timestamp=time.time(), source_boot_ms=sample['source_boot_ms'],
                    reason='cached_source_packet_not_a_new_measurement'))
                await asyncio.sleep(1. / scenario.visual.rate_hz)
                continue
            measurement_epoch = observation.timestamp
            evidence = app._target_evidence_snapshot(observation)
            accepted = await app._dispatch_tracker_output_on_flight_loop(observation)
            continuity = app.get_target_continuity_status()
            typed = observation.gimbal_observation
            received_loss = (typed.tracking_state == 'TARGET_LOST' if typed is not None
                             else lost and not observation.tracking_active)
            row = dict(timestamp=measurement_epoch, elapsed_s=elapsed, target_ned=target,
                       image_position=coordinates if not lost else None, loss_active=received_loss,
                       scheduled_loss_active=lost, target_evidence_state=evidence.state.value,
                       continuity=continuity,
                       measurement_target_ned=observation.raw_data['measurement_target_ned'],
                       fixture_kind=observation.raw_data['fixture_kind'], angular=observation.angular,
                       gimbal_observation=asdict(observation.gimbal_observation) if observation.gimbal_observation is not None else None,
                       image_measurement=asdict(observation.image_measurement) if observation.image_measurement is not None else None,
                       **sample)
            records.append(row)
            retain_pose(sample, measurement_epoch)
            log("trace/follower_state.jsonl", dict(timestamp=measurement_epoch, **continuity))
            if not accepted and (not scenario.expected_handoff or app.following_active):
                raise RuntimeError("Production dispatch refused a nominal measurement")
            await asyncio.sleep(1. / scenario.visual.rate_hz)
        cleanup = getattr(app, '_following_stop_future', None)
        if not app.following_active and cleanup is not None:
            async def completed_teardown():
                return await asyncio.shield(cleanup)
            await observe_handoff(completed_teardown())
        before_cleanup = dict(following_active=app.following_active,
            handoff=getattr(app, '_last_following_handoff', None),
            continuity=app.get_target_continuity_status(), configured_continuity_policy=resolved_policy)
        tracker_records = [json.loads(line) for line in (output / 'trace/tracker_command_trace.jsonl').read_text().splitlines()
                           if line.strip()]
        fault_checks = evaluate_fault_outcome(scenario, records,
            following_active=before_cleanup['following_active'], handoff=before_cleanup['handoff'],
            retarget_count=retarget_count, takeover_requested_at=takeover_requested_at,
            mode_calls=mode_calls, telemetry_outage_injected=telemetry_outage_injected,
            configured_policy=resolved_policy, tracker_records=tracker_records)
        write_json(output / 'fault-outcome-before-cleanup.json', dict(**before_cleanup, checks=fault_checks))
        if app.following_active:
            await observe_handoff(app._stop_following_after_continuity_failure("operator_stop"))
        handoff = getattr(app, "_last_following_handoff", {})
        stop_count = len(publications)
        convergence = []
        deadline = time.monotonic() + manager.get_mavsdk_command_timeout_s()
        while time.monotonic() < deadline:
            sample = await snapshot()
            convergence.append(sample)
            if sample["hold"]:
                break
            await asyncio.sleep(.15)
        write_json(output / "stop-mode-convergence.json", convergence)
        after = []
        for _ in range(7):
            await asyncio.sleep(.15)
            after.append(await snapshot())
        write_json(output / "post-stop-observations.json", after)
        checks = dict(
            hold_confirmed=(handoff.get("result") == ("stopped" if takeover_requested_at is not None else "confirmed_hold")
                            and bool(convergence) and convergence[-1]["hold"]
                            and all(s["hold"] for s in after)),
            no_publication_after_stop=len(publications) == stop_count,
            no_following_replay=not app.following_active,
            sdk_mode_call_evidence_complete=not mode_recording_errors,
            **fault_checks,
        )
        if scenario.takeover_at_s is not None:
            quiesce = (takeover_cleanup or {}).get("sender_quiesce", {})
            checks["takeover_released_without_backend_hold"] = (
                not (takeover_cleanup or {}).get("errors")
                and quiesce.get("authority_released") is True
                and quiesce.get("local_sender_quiesced") is True
                and quiesce.get("vehicle_hold_acknowledged") is False
                and "offboard_stop_action" not in (takeover_cleanup or {})
            )
            write_json(output / "takeover-cleanup.json", takeover_cleanup)
        Parameters.FOLLOWER_CIRCUIT_BREAKER = True
        gate = _evaluate_px4_command_gate("mc_sih_post_stop_probe")
        checks["post_stop_circuit_breaker"] = gate.blocked and not gate.degraded and gate.reason == "circuit_breaker_active"
        report = evaluate_response(response_scenario, records, publications,
            velocity_limits=concrete.velocity_limits._asdict(),
            rate_limits_deg_s={f"{axis}speed_deg_s": math.degrees(getattr(concrete.rate_limits, axis))
                               for axis in ("yaw", "pitch", "roll")},
            attitude_limits_deg={"roll": config["MC_ATTITUDE_RATE"]["MAX_ROLL_ANGLE"],
                                 "pitch": config["MC_ATTITUDE_RATE"]["MAX_PITCH_ANGLE"]},
            publication_gap_limit_s=min(commander.get_status()["command_ttl_s"],
                                        commander.get_status()["publish_timeout_s"]),
            expected_rejection_after_monotonic_s=telemetry_outage_started_at)
        report["checks"].update(checks)
        report.update(passed=all(report["checks"].values()), scope="actual_mc_follower_component_only",
                      follower=args.follower, physical_camera=False, application_startup_qualified=False,
                      hardware_qualified=False, release_qualified=False, handoff=handoff,
                      publication=commander.get_status(), camera=asdict(scenario.camera) if scenario.camera is not None else None,
                      fixture_kind='simulated_boresight' if family == 'angles' else 'simulated_fixed_camera_projection',
                      physical_selection_api_qualified=False,
                      sdk_mode_call_observer_scope=['action.hold', 'offboard.stop'],
                      configured_continuity_policy=resolved_policy,
                      altitude_guidance=scenario.visual.altitude_control,
                      metric_scope="Observed bearing/image alignment from actual pose; range closure does not prove interception",
                      executed_scenario_sha256=hashlib.sha256((output / "scenario.yaml").read_bytes()).hexdigest(),
                      direct_rate_altitude_settings=config["MC_ATTITUDE_RATE"] if args.follower == "mc_attitude_rate" else None)
        write_json(output / "result.json", report)
        if not report["passed"]:
            raise RuntimeError("MC scenario failed its frozen response/authority checks")
    finally:
        Parameters.FOLLOWER_CIRCUIT_BREAKER = False
        try:
            if getattr(app, "offboard_commander", None):
                await app.offboard_commander.stop()
            if manager.active_mode:
                await manager.stop_offboard_mode()
            if armed:
                await manager.drone.action.land()
        finally:
            try:
                await manager.stop()
            finally:
                mode_observer.close()
                if report is not None:
                    # Keep the pre-operator outcome, but include SDK calls made
                    # by final cleanup in the takeover/no-extra-Hold proof.
                    report['checks'].update(evaluate_fault_outcome(scenario, records,
                        following_active=before_cleanup['following_active'], handoff=before_cleanup['handoff'],
                        retarget_count=retarget_count, takeover_requested_at=takeover_requested_at,
                        mode_calls=mode_calls, telemetry_outage_injected=telemetry_outage_injected,
                        configured_policy=resolved_policy, tracker_records=tracker_records))
                    report['checks']['sdk_mode_call_evidence_complete'] = not mode_recording_errors
                    report['passed'] = all(report['checks'].values())
                    write_json(output / 'result.json', report)
            if gimbal_source is not None:
                gimbal_source.close()
            app.mavlink_data_manager.stop_polling()
            observer.stop_polling()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--follower", required=True)
    parser.add_argument("--mount", default="HORIZONTAL")
    args = parser.parse_args()
    if not args.worker:
        parser.error("Use run_sih_follower_validation.py; this entry only serves the isolated worker")
    try:
        asyncio.run(worker(args))
    except Exception as exc:
        output = Path("/work/evidence")
        if os.environ.get("EVIDENCE_OWNER") and output.is_dir():
            if not (output / "result.json").exists():
                write_json(output / "result.json", dict(passed=False, follower=args.follower,
                    reason=str(exc), scope="actual_mc_follower_component_only", hardware_qualified=False))
        raise


if __name__ == "__main__":
    main()
