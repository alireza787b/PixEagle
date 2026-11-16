#!/usr/bin/env python3
"""Isolated stock-PX4 application lifecycle qualification; no physical IO.

Runs the production controller, tracker, follower, continuity and command owner.
Camera observations are independent SIH world-target projections. HTTP/client
and physical-camera qualification remain separate gates.
"""

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def application_metrics(rows, *, altitude_control):
    """Actual pose only; a successful submission never supplies vehicle motion."""
    active = [row for row in rows if row["following_active"]]
    if not active:
        return {"passed": False, "reason": "no_active_px4_observations"}
    distances = [math.dist(row["vehicle_ned"], row["target_ned"]) for row in active]
    origin_down = active[0]["vehicle_ned"][2]
    altitude_error = max(abs(row["vehicle_ned"][2] - origin_down) for row in active)
    lost = [row for row in active if row["target_lost"]]
    recovered = bool(lost) and any(row["elapsed_s"] > lost[-1]["elapsed_s"]
        and row["continuity"]["authority_state"] == "ACTIVE" for row in active)
    input_failures = sorted({row["follower_input_reason"] for row in active if row["follower_input_reason"]})
    return dict(passed=recovered and not input_failures and min(distances) < .75 * distances[0]
        and (altitude_control or altitude_error < 5.), initial_range_m=distances[0],
        closest_range_m=min(distances), final_range_m=distances[-1],
        engagement_altitude_error_m=altitude_error, loss_recovered=recovered,
        guidance_input_failures=input_failures)


def render_application_report(evidence_root):
    """Adapt retained evidence to the existing read-only viewer, not another UI."""
    import hashlib
    import yaml
    from classes.aircraft_state import Quaternion, Vector3, fixed_wing_control_attitude
    from classes.sih_visualization import VisualizationScenario, analyze_timeline, build_timeline, read_jsonl, write_csv
    from tools.sih_visualizer import build_html, write_png

    root = Path(evidence_root)
    rows = read_jsonl(root / "observations.jsonl")
    manifest = json.loads((root / "manifest.json").read_text())
    result = json.loads((root / "result.json").read_text())
    config = yaml.safe_load((root / "configs/config.yaml").read_text())
    active = [row for row in rows if row["following_active"]]
    if not active:
        raise ValueError("application_report_has_no_observed_active_pose")
    fixed_wing = any(row.get("aircraft_phase") == "fixed_wing" for row in active)
    if not any(row.get("aircraft_phase") for row in active):
        # Older evidence has no per-sample phase; retain that unknown in samples.
        fixed_wing = result["final_flight_state"].get("phase_observation", {}).get("phase") == "fixed_wing"
    report = root / "visualization"
    report.mkdir(exist_ok=True)
    template = yaml.safe_load((ROOT / "tools/sih_visualization_scenarios/gimbal-vector-native-fw.yaml").read_text())
    template.update(name=root.name, mount_type=manifest["mount"], airframe="fixed_wing" if fixed_wing else "vtol",
        stable_flight={"required": False}, initial_conditions={"vehicle_ned": active[0]["vehicle_ned"]})
    template["follower"].update(purpose="Stock MAVLink application lifecycle · simulated gimbal observations",
        command_contract="fixed_wing_external" if fixed_wing else "vtol_external",
        altitude_control=config["Follower"]["FollowerOverrides"]["GM_VELOCITY_VECTOR"]["ENABLE_ALTITUDE_CONTROL"])
    template["constraints"]["altitude"] = {"min": config["Safety"]["GlobalLimits"]["MIN_ALTITUDE"],
        "max": config["Safety"]["GlobalLimits"]["MAX_ALTITUDE"]}
    template["target"]["waypoints"] = [{"time_s": row["timestamp"] - rows[0]["timestamp"],
        "position_ned": row["target_ned"]} for row in (rows[0], rows[-1])]
    scenario_path = report / "scenario.yaml"
    scenario_path.write_text(yaml.safe_dump(template, sort_keys=False))
    scenario = VisualizationScenario.from_yaml(scenario_path)
    poses = []
    states = []
    for row in rows:
        pose = dict(timestamp=row["timestamp"], vehicle_ned=row["vehicle_ned"],
            vehicle_quaternion=row["quaternion_wxyz"], source="px4_mavlink_observed")
        if row.get("aircraft_phase") == "fixed_wing":
            forward = fixed_wing_control_attitude(Quaternion(*row["quaternion_wxyz"]),
                is_tailsitter=manifest["simulator_model"] == "sihsim_xvert").rotate(Vector3(1., 0., 0.))
            pose["native_fw_forward_ned"] = [forward.x, forward.y, forward.z]
        poses.append(pose)
        states.append(dict(timestamp=row["timestamp"], state=row["continuity"]["authority_state"],
            aircraft_phase=row.get("aircraft_phase"), limiting_reason=row["continuity"]["reason_code"]))
    evidence = dict(pose=poses, state=states,
        target=[dict(timestamp=row["timestamp"], target_ned=row["target_ned"]) for row in rows],
        tracker=read_jsonl(root / "trace/tracker_command_trace.jsonl"),
        published=read_jsonl(root / "trace/offboard_publish_trace.jsonl"))
    samples = build_timeline(scenario, evidence)
    summary = analyze_timeline(scenario, samples)
    summary.update(qualification_result=result,
        claim_boundary="PX4-observed application lifecycle; simulated camera. HTTP, QGC and hardware remain separate.",
        input_sha256={name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
            "manifest.json", "observations.jsonl", "result.json", "trace/tracker_command_trace.jsonl",
            "trace/offboard_publish_trace.jsonl")})
    (report / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (report / "trace.json").write_text(json.dumps([sample.to_dict() for sample in samples], indent=2) + "\n")
    write_csv(report / "trace.csv", samples)
    (report / "index.html").write_text(build_html(scenario, samples, summary))
    write_png(report / "summary.png", scenario, samples)


async def worker(args):
    import requests
    from classes.app_controller import AppController
    from classes.mavlink_data_manager import MavlinkDataManager
    from classes.parameters import Parameters
    from classes.px4_interface_manager import PX4InterfaceManager
    from classes.tracker_trace import TrackerTraceRecorder
    from classes.stock_mavlink_setpoints import PX4_HOLD_MODE
    from mc_follower_sih import PoseProgress, pose_observation, request_telemetry_identity
    from sih_gimbal_world_target import SihGimbalWorldTarget

    output = Path("/work/evidence")
    manifest = json.loads((output / "manifest.json").read_text())
    if (not os.environ.get("EVIDENCE_OWNER") or set(os.listdir("/sys/class/net")) != {"lo"}
            or manifest.get("network") != "none" or manifest.get("host_ports") != []
            or manifest.get("sih_baseline", {}).get("firmware", {}).get("policy") != "stock"):
        raise RuntimeError("Isolated stock SIH evidence owner required")

    def record(name, row):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as stream:
            stream.write(json.dumps(row, default=str) + "\n")

    def save(name, row):
        (output / name).write_text(json.dumps(row, indent=2, default=str) + "\n")

    # Controller-only fixture: media/HTTP/UI workers are intentionally absent.
    # Every flight lifecycle method below is the production implementation.
    app = AppController.__new__(AppController)
    app.bind_flight_event_loop(asyncio.get_running_loop())
    app._startup_component_lock = threading.Lock()
    app._startup_components = {}
    app._follower_state_lock = asyncio.Lock()
    app._tracker_model_state_lock = threading.RLock()
    app._tracking_session_generation = 0
    app._following_session_id = None
    app._airframe_follow_binding = None
    app.follower = app.offboard_commander = app.setpoint_sender = None
    app.following_active = app._following_stopping = app.shutdown_flag = False
    app.following_execution_mode = "PX4"
    app.tracking_started = True
    app.smart_mode_active = False
    app.estimator = None
    app.telemetry_handler = SimpleNamespace(follower=None)
    app.mavlink_data_manager = MavlinkDataManager("127.0.0.1", 8088, .1, Parameters.MAVLINK_DATA_POINTS)
    manager = PX4InterfaceManager(app)
    app.px4_interface = app._active_following_controller = manager
    app.mavlink_data_manager.register_offboard_exit_callback(app._schedule_offboard_mode_exit)
    app._get_video_frame_status_for_following = lambda: dict(source="none", usable_for_following=False, replay_source=False)
    app.tracker_trace_recorder = TrackerTraceRecorder(
        tracker_command_trace_path=output / "trace/tracker_command_trace.jsonl",
        offboard_publish_trace_path=output / "trace/offboard_publish_trace.jsonl",
        source="stock_application_sih")
    camera = SihGimbalWorldTarget(app, progress=PoseProgress())
    pump = None
    rows = []
    adjusted = False
    accepted = 0
    target_origin = None
    target_velocity = None
    began = None
    commander = None
    stop_result = None
    mode_requests = []
    original_send = None

    async def wait_for(predicate, timeout=60.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            await asyncio.sleep(.1)
        raise RuntimeError("Simulated readiness deadline expired")

    async def snapshot():
        payload = await asyncio.to_thread(lambda: requests.get("http://127.0.0.1:8088/v1/mavlink", timeout=2).json())
        return pose_observation(payload, app.mavlink_data_manager.get_flight_state(), manager,
            expected_aircraft_uid=manager.get_aircraft_identity()["autopilot_uid"])

    async def observe_target():
        nonlocal accepted
        while True:
            sample = await snapshot()
            elapsed = time.monotonic() - began
            target = tuple(target_origin[i] + target_velocity[i] * elapsed for i in range(3))
            lost = 8. <= elapsed < 9.
            tracker = camera.observe(sample, target, epoch_s=time.time(), lost=lost)
            if app.following_active and tracker is not None:
                accepted += bool(await app._follow_tracker_output(tracker))
            row = dict(timestamp=time.time(), elapsed_s=elapsed, vehicle_ned=sample["position_ned"],
                quaternion_wxyz=sample["quaternion_wxyz"], target_ned=target, target_lost=lost,
                source_boot_ms=sample["source_boot_ms"], following_active=app.following_active,
                aircraft_phase=app.mavlink_data_manager.get_flight_state().get("phase_observation", {}).get("phase"),
                follower_input_reason=getattr(getattr(app.follower, "follower", None), "_telemetry_metadata", {}).get("guidance_input_reason"),
                continuity=app.get_target_continuity_status(),
                controls=[] if app.follower is None else app.follower.follower.session_controls())
            rows.append(row)
            record("observations.jsonl", row)
            await asyncio.sleep(.05)

    try:
        app.mavlink_data_manager.start_polling()
        await manager.connect()
        original_send = manager.drone.mavlink_direct.send_message
        async def observe_send(message):
            if message.message_name == "COMMAND_LONG":
                event = dict(monotonic_s=time.monotonic(), fields=json.loads(message.fields_json))
                mode_requests.append(event)
                record("mavlink-direct-requests.jsonl", event)
            return await original_send(message)
        manager.drone.mavlink_direct.send_message = observe_send
        await wait_for(lambda: manager.is_command_connection_ready(require_fresh_telemetry=True))
        await manager.observe_aircraft_identity()
        await asyncio.to_thread(request_telemetry_identity, requests)
        await wait_for(lambda: app.mavlink_data_manager.get_flight_state().get("fresh") is True)
        Parameters.FOLLOWER_CIRCUIT_BREAKER = False
        async def armable():
            async for health in manager.drone.telemetry.health():
                if health.is_armable:
                    return
        await asyncio.wait_for(armable(), timeout=45.)
        fixed_wing = args.airframe == "sihsim_airplane" or args.start_phase == "fixed_wing"
        takeoff_altitude = 80. if fixed_wing else 40.
        await manager.drone.action.set_takeoff_altitude(takeoff_altitude)
        await manager.drone.action.arm()
        await manager.drone.action.takeoff()
        await wait_for(lambda: manager.current_altitude is not None and manager.current_altitude > takeoff_altitude - 3.)
        await manager.drone.action.hold()
        await asyncio.sleep(8.)
        if args.airframe == "sihsim_xvert" and fixed_wing:
            await manager.drone.action.transition_to_fixedwing()
            await wait_for(lambda: app.mavlink_data_manager.get_flight_state().get("phase_observation", {}).get("phase") == "fixed_wing")
            await asyncio.sleep(5.)
        await app.refresh_airframe_following_state(args.follower)
        if args.airframe != "sihsim_quadx":
            await wait_for(lambda: manager.guidance_start_context is not None)
        sample = await snapshot()
        state = manager.get_aircraft_state()
        heading = state.navigation_heading_rad if state is not None else math.radians(manager.current_yaw)
        forward, lateral, target_speed = (180., 30., 3.) if fixed_wing else (15., 2., .3)
        target_origin = (sample["position_ned"][0] + forward*math.cos(heading) - lateral*math.sin(heading),
            sample["position_ned"][1] + forward*math.sin(heading) + lateral*math.cos(heading),
            sample["position_ned"][2] + (40. if args.unconstrained else 0.))
        target_velocity = (target_speed*math.cos(heading), target_speed*math.sin(heading), 0.)
        began = time.monotonic()
        pump = asyncio.create_task(observe_target())
        await wait_for(lambda: camera.measurement is not None)
        save("start-readiness.json", app._get_follow_start_readiness())
        result = await app.connect_px4()
        save("start-result.json", result)
        if result["errors"] or not app.following_active:
            raise RuntimeError("Application Follow Start failed: " + str(result))
        commander = app.offboard_commander
        while time.monotonic() - began < 22.:
            if pump.done():
                await pump
            if not app.following_active:
                raise RuntimeError("Application ended following unexpectedly")
            elapsed = time.monotonic() - began
            controls = app.follower.follower.session_controls()
            if elapsed > 12. and controls and not adjusted:
                control = controls[0]
                value = max(control["minimum"], control["value"] - control["step"])
                # Same typed follower operation used by the actions service;
                # transport/auth/HTTP qualification is deliberately not claimed.
                app.follower.follower.update_session_control(control["control_id"], value, control["revision"])
                adjusted = True
            await asyncio.sleep(.05)
        save("commander-before-stop.json", commander.get_status())
        pilot_requested_at = None
        if args.finish in {"pilot_return", "pilot_transition"}:
            pilot_requested_at = time.monotonic()
            if args.finish == "pilot_return":
                await manager.drone.action.return_to_launch()
            else:
                await manager.drone.action.transition_to_multicopter()
            await wait_for(lambda: not app.following_active, timeout=10.)
            if args.finish == "pilot_transition":
                await wait_for(lambda: app.mavlink_data_manager.get_flight_state().get("phase_observation", {}).get("phase") == "multicopter", timeout=30.)
        stop_result = await app.disconnect_px4()
        save("stop-result.json", stop_result)
        await asyncio.sleep(.5)
        flight = app.mavlink_data_manager.get_flight_state()
        status = commander.get_status()
        metrics = application_metrics(rows, altitude_control=args.unconstrained)
        mode_preserved = flight.get("flight_mode") == PX4_HOLD_MODE
        if pilot_requested_at is not None:
            expected = (manager.get_flight_mode_text(flight.get("flight_mode")) == "Return"
                if args.finish == "pilot_return" else
                flight.get("phase_observation", {}).get("phase") == "multicopter"
                and flight.get("flight_mode") != app.mavlink_data_manager.offboard_mode_code)
            mode_preserved = expected and not any(row["monotonic_s"] >= pilot_requested_at for row in mode_requests)
        save("result.json", dict(passed=not stop_result["errors"] and not app.following_active
            and flight.get("fresh") is True and mode_preserved
            and accepted > 20 and adjusted and metrics["passed"], metrics=metrics,
            actual_px4_pose=True, application_lifecycle=True,
            physical_camera=False, http_client_qualified=False, speed_adjusted=adjusted,
            finish=args.finish, pilot_mode_preserved=mode_preserved,
            accepted_tracker_updates=accepted, commander=status, handoff=app._last_following_handoff,
            retained_samples=len(rows), final_flight_state=flight))
        if not json.loads((output / "result.json").read_text())["passed"]:
            raise RuntimeError("Application qualification acceptance failed")
    finally:
        if pump is not None:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
        if app.following_active or app._airframe_follow_binding is not None:
            save("cleanup-result.json", await app.disconnect_px4())
        watchdog = getattr(app, "_continuity_watchdog_task", None)
        if watchdog is not None:
            watchdog.cancel()
            await asyncio.gather(watchdog, return_exceptions=True)
        camera.close()
        if original_send is not None:
            manager.drone.mavlink_direct.send_message = original_send
        app.mavlink_data_manager.stop_polling()
        await manager.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--unconstrained", action="store_true")
    parser.add_argument("--airframe", choices=["sihsim_airplane", "sihsim_quadx", "sihsim_xvert"], default="sihsim_airplane")
    parser.add_argument("--start-phase", choices=["multicopter", "fixed_wing"], default="multicopter")
    parser.add_argument("--finish", choices=["stop", "pilot_return", "pilot_transition"], default="stop")
    parser.add_argument("--follower", choices=["gm_velocity_vector"], default="gm_velocity_vector")
    parser.add_argument("--mount", choices=["HORIZONTAL", "VERTICAL"], default="VERTICAL")
    parser.add_argument("--backend-repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--simulation-build-manifest", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--bin-dir", type=Path, default=ROOT / "bin")
    parser.add_argument("--opencv-lib", type=Path, default=Path("/usr/lib/x86_64-linux-gnu"))
    args = parser.parse_args()
    if args.finish == "pilot_transition" and (args.airframe != "sihsim_xvert" or args.start_phase != "fixed_wing"):
        parser.error("Transition stimulus requires the isolated tailsitter initially in FW")
    if args.worker:
        asyncio.run(asyncio.wait_for(worker(args), timeout=220.))
        return
    if not args.execute or args.output is None or args.simulation_build_manifest is None:
        parser.error("Explicit --execute, new --output and stock --simulation-build-manifest required")
    from tools.sih_isolated_host import host
    args.simulator_model = args.airframe
    args.evidence_kind = "stock-mavlink-application-lifecycle"
    args.worker_extra_args = ["--airframe", args.airframe, "--start-phase", args.start_phase,
        "--finish", args.finish] + (["--unconstrained"] if args.unconstrained else [])
    def configure(config):
        from tools.run_mavlink_fw_vector_sih import configure_component
        configure_component(config, unconstrained=args.unconstrained)
        if args.airframe != "sihsim_airplane":
            config["GM_VELOCITY_VECTOR"]["REQUESTED_SPEED"] = 1.5
            config["Safety"]["GlobalLimits"].update(MAX_VELOCITY=3., MAX_VELOCITY_FORWARD=3.,
                MAX_VELOCITY_LATERAL=3., MAX_VELOCITY_VERTICAL=3.)
        for name in ("mc_follower_sih.py", "fixed_camera_world_target.py", "sih_gimbal_world_target.py"):
            shutil.copyfile(args.backend_repo / "tools" / name, args.output / "backend/tools" / name)
        config["Follower"]["FOLLOWER_DATA_REFRESH_RATE"] = 20.
    host(args, driver_path=Path(__file__), configure=configure)
    render_application_report(args.output)


if __name__ == "__main__":
    main()
