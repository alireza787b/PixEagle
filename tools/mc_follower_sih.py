"""Actual MC image-follower component qualification in an owned isolated SIH namespace.

The host launcher is shared infrastructure. This worker uses production target
dispatch, continuity, follower and MAVSDK publication, with simulated image
measurements instead of a real camera. It does not qualify HTTP/App startup.
"""

from __future__ import annotations

import argparse
import asyncio
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
    from tools.fixed_camera_world_target import MCScenario, evaluate_response, stable_hold_window
    from tools.sitl_gimbal_geometry_fixture import pose_from_mavlink2rest
except ModuleNotFoundError:
    from fixed_camera_world_target import MCScenario, evaluate_response, stable_hold_window
    from sitl_gimbal_geometry_fixture import pose_from_mavlink2rest


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=lambda item: item.value) + "\n", encoding="utf-8")


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
    args.mount = "HORIZONTAL"
    args.simulator_model = "sihsim_quadx"
    args.evidence_kind = "mc-fixed-camera-world-target-component"
    args.worker_extra_args = []

    def configure(config):
        stage = args.output.resolve()
        for name in ("fixed_camera_world_target.py", "mc_follower_sih.py"):
            shutil.copyfile(ROOT / "tools" / name, stage / "backend/tools" / name)
        import yaml
        staged_scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        staged_scenario["follower"]["altitude_control"] = scenario.visual.altitude_control
        config["Tracking"]["DEFAULT_TRACKING_ALGORITHM"] = "CSRT"
        telemetry_source = getattr(args, "telemetry_source", "mavlink2rest")
        if telemetry_source not in {"mavlink2rest", "mavsdk"}:
            raise ValueError("Unsupported MC control telemetry source")
        config["Follower"]["USE_MAVLINK2REST"] = telemetry_source == "mavlink2rest"
        config["Follower"]["FollowerOverrides"].setdefault(args.follower.upper(), {})[
            "ENABLE_ALTITUDE_CONTROL"
        ] = scenario.visual.altitude_control
        if args.follower == "mc_velocity_ground":
            config["MC_VELOCITY_GROUND"]["ENABLE_DESCEND_TO_TARGET"] = scenario.visual.altitude_control
        # Direct-rate altitude/thrust settings remain their declared saved values.
        limits = {**config["Safety"]["GlobalLimits"],
                  **config["Safety"]["FollowerOverrides"].get(args.follower.upper(), {})}
        staged_scenario["constraints"] = {
            "velocity": {"forward": limits["MAX_VELOCITY_FORWARD"], "right": limits["MAX_VELOCITY_LATERAL"],
                         "down": limits["MAX_VELOCITY_VERTICAL"] if scenario.visual.altitude_control else 0.},
            "rate": {"yaw": limits["MAX_YAW_RATE"]},
            "altitude": {"min": limits["MIN_ALTITUDE"], "max": limits["MAX_ALTITUDE"]},
        }
        staged_scenario["continuity_policy"] = {"mode": config["TargetContinuity"]["MODE"]}
        (stage / "scenario.yaml").write_text(yaml.safe_dump(staged_scenario, sort_keys=False))
        write_json(stage / "harness-inputs.json", {
            "scenario_sha256": hashlib.sha256((stage / "scenario.yaml").read_bytes()).hexdigest(),
            "source_scenario_sha256": hashlib.sha256(scenario_path.read_bytes()).hexdigest(),
            "qualification_scope": "MC component with simulated fixed-camera measurements",
            "control_telemetry_source": telemetry_source,
            "camera_projection": asdict(scenario.camera),
            "tools": {name: hashlib.sha256((ROOT / "tools" / name).read_bytes()).hexdigest()
                      for name in ("fixed_camera_world_target.py", "mc_follower_sih.py", "sih_isolated_host.py")},
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
        hold=manager.get_flight_mode_text(flight_state.get("flight_mode")) == "Hold",
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
    app.telemetry_handler = SimpleNamespace(follower=None)
    app._following_session_id = uuid.uuid4().hex
    app._following_stopping = False
    app.mavlink_data_manager.register_offboard_exit_callback(app._schedule_offboard_mode_exit)
    app.camera_runtime = SimpleNamespace(provider=None)
    app._get_video_frame_status_for_following = lambda: dict(
        source="simulated_fixed_camera", usable_for_following=True, replay_source=False,
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
    records, publications = [], []
    armed = False

    def log(name, row):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")

    def publication(event):
        app._record_offboard_publish_result(event)
        intent = event.get("command_intent")
        publications.append(dict(timestamp=time.time(), monotonic_s=time.monotonic(),
                                 success=event["publish_status"]["last_publish_success"] is True,
                                 fields=event.get("submitted_fields") if intent is None else dict(intent.fields),
                                 submitted_fields=event.get("submitted_fields"), attempted=event.get("publication_attempted"),
                                 command_ready=manager.is_command_connection_ready(require_fresh_telemetry=True)))

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

    async def wait_for(predicate, timeout=60.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            await asyncio.sleep(.1)
        raise RuntimeError("Simulated aircraft readiness deadline expired")

    try:
        app.mavlink_data_manager.start_polling()
        observer.start_polling()
        await manager.connect()
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
        if scenario.camera.project(sample["position_ned"], sample["quaternion_wxyz"], initial_target) is None:
            raise RuntimeError("Frozen world target is not visible from the actual settled aircraft pose")
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
        response_scenario = MCScenario.from_yaml(output / "scenario.yaml")
        write_json(output / "runtime-policy.json", dict(continuity=resolved_policy,
            velocity=concrete.velocity_limits._asdict(), altitude=concrete.altitude_limits._asdict(),
            rates_rad_s=concrete.rate_limits._asdict(), pid_gains=config["PID"]["PID_GAINS"]))
        commander = OffboardCommander(manager, concrete.setpoint_handler, on_publish_result=publication)
        app.offboard_commander = commander
        if not (await manager.start_offboard_mode()).get("executed"):
            raise RuntimeError("Production Offboard start failed")
        seed = CommandIntent(args.follower, app.follower.get_control_type(),
                             concrete.setpoint_handler.get_fields(), "isolated_sih_baseline")
        if not commander.submit_intent(seed):
            raise RuntimeError("Initial complete safe command was refused")
        await commander.start()
        app.following_active = True
        started = time.monotonic()
        progress_guard = PoseProgress()
        expected_loss_seen = False
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
                await manager.drone.action.hold()
                await wait_for(lambda: not app.following_active, timeout=manager.get_mavsdk_command_timeout_s())
                cleanup = getattr(app, "_following_stop_future", None)
                if cleanup is not None:
                    takeover_cleanup = await asyncio.shield(cleanup)
                break
            target = scenario.target_at(elapsed, anchor)
            if target is None:
                break
            log("trace/target_truth.jsonl", dict(timestamp=time.time(), target_ned=target))
            progress = sample["source_boot_ms"]
            if not progress_guard.accept(progress, time.monotonic()):
                log("skipped-pose-polls.jsonl", dict(timestamp=time.time(), source_boot_ms=progress,
                    reason="cached_source_packet_not_a_new_measurement"))
                await asyncio.sleep(1. / scenario.visual.rate_hz)
                continue
            coordinates = scenario.camera.project(sample["position_ned"], sample["quaternion_wxyz"], target)
            due = sum(at <= elapsed for at, _offset in scenario.retargets)
            while retarget_count < due:
                if coordinates is None:
                    raise RuntimeError("Retarget candidate is outside the camera FOV; ownership remains unchanged")
                before = app.get_target_continuity_status()
                transition = app._prepare_following_target_transition("sih_operator_retarget")
                if not transition.get("prepared"):
                    raise RuntimeError("Production retarget preparation was refused")
                app._advance_tracking_session_generation(for_retarget=True)
                after = app.get_target_continuity_status()
                log("fault-events.jsonl", dict(timestamp=time.time(), event="retarget", before=before,
                    after=after, generation=app._tracking_session_generation, transition=transition))
                if before.get("target_transition_pending") and (
                        after.get("episode_id") != before.get("episode_id")
                        or after.get("coast_distance_m", 0.) < before.get("coast_distance_m", 0.)
                        or after.get("loss_elapsed_s", 0.) < before.get("loss_elapsed_s", 0.)):
                    raise RuntimeError("Repeated retarget reset the active recovery episode or travel budget")
                retarget_count += 1
            lost = any(start <= elapsed < end for start, end in scenario.loss_windows)
            expected_loss_seen |= lost
            if coordinates is None and not lost:
                raise RuntimeError("Independent world target left the declared fixed-camera FOV")
            measurement_epoch = time.time()
            observation = tracker_observation(coordinates, measurement_epoch_s=measurement_epoch,
                                              measurement_monotonic_s=sample["monotonic_s"], lost=lost,
                                              target_id=retarget_count)
            accepted = await app._dispatch_tracker_output_on_flight_loop(observation)
            row = dict(timestamp=measurement_epoch, elapsed_s=elapsed, target_ned=target,
                       image_position=coordinates if not lost else None, loss_active=lost, **sample)
            records.append(row)
            log("px4/pose_trace.jsonl", dict(timestamp=measurement_epoch, vehicle_ned=sample["position_ned"],
                vehicle_quaternion=sample["quaternion_wxyz"], source=sample["source"],
                source_boot_ms=sample["source_boot_ms"]))
            log("trace/follower_state.jsonl", dict(timestamp=measurement_epoch, **app.get_target_continuity_status()))
            if not accepted and (not scenario.expected_handoff or app.following_active):
                raise RuntimeError("Production dispatch refused a nominal measurement")
            await asyncio.sleep(1. / scenario.visual.rate_hz)
        if app.following_active:
            await app._stop_following_after_continuity_failure("operator_stop")
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
            expected_faults_executed=(expected_loss_seen == bool(scenario.loss_windows)
                                     and (takeover_requested_at is not None) == (scenario.takeover_at_s is not None)
                                     and retarget_count == len(scenario.retargets)
                                     and telemetry_outage_injected == (scenario.telemetry_outage is not None)),
            no_following_replay=not app.following_active,
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
                      publication=commander.get_status(), camera=asdict(scenario.camera),
                      altitude_guidance=scenario.visual.altitude_control,
                      metric_scope="Observed image alignment from actual pose; range closure is checked separately and does not prove interception",
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
            await manager.stop()
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
