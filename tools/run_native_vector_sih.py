#!/usr/bin/env python3
"""Exercise production native Vector components on an already airborne SIH.

Dry-run by default. This tool never arms, takes off, transitions or flashes.
It verifies an isolated Docker SIH process before acquiring native authority.
The HTTP/App startup path is outside this component-level qualification.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from classes.aircraft_state import AircraftBinding, AircraftState, AircraftStateOwner, AirframePhase, GuidanceSessionIdentity  # noqa: E402
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy  # noqa: E402
from classes.follower import FollowerFactory  # noqa: E402
from classes.native_follow_binding import NativeFollowBinding  # noqa: E402
from classes.native_guidance import NativeGuidanceClient  # noqa: E402
from classes.offboard_commander import OffboardCommander  # noqa: E402
from classes.parameters import Parameters  # noqa: E402
from classes.sih_visualization import VisualizationScenario  # noqa: E402
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor, TargetEvidenceSnapshot  # noqa: E402
from classes.tracker_output import TrackerDataType, TrackerOutput  # noqa: E402
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target  # noqa: E402


def command(*args):
    return subprocess.check_output(args, text=True, timeout=15)


def verify_simulator(container: str, instance: int, socket: Path) -> dict:
    info = json.loads(command("docker", "inspect", container))[0]
    if (info["HostConfig"]["NetworkMode"] == "host" or info["HostConfig"]["Privileged"]
            or info["HostConfig"].get("Devices") or info["NetworkSettings"]["Ports"]):
        raise ValueError("SIH requires an isolated container without hardware or published ports")
    # Inspect the real process and inherited model, not an operator-supplied label.
    script = """import json, pathlib
out=[]
for p in pathlib.Path('/proc').iterdir():
 try:
  args=(p/'cmdline').read_bytes().split(b'\\0'); args=[x.decode() for x in args if x]
  env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode().split('\\0') if '=' in x)
  if args and args[0].endswith('/build/px4_sitl_sih/bin/px4'):
   out.append(dict(args=args, model=env.get('PX4_SIM_MODEL'), cwd=str((p/'cwd').resolve())))
 except (OSError, UnicodeError): pass
print(json.dumps(out))
"""
    matches = [p for p in json.loads(command("docker", "exec", "--user", str(socket.stat().st_uid),
                                            container, "python3", "-c", script))
               if "-i" in p["args"] and p["args"][p["args"].index("-i") + 1] == str(instance)]
    if len(matches) != 1 or not str(matches[0]["model"]).startswith("sihsim_"):
        raise ValueError("An unambiguous running PX4 SIH instance is required")
    process = matches[0]
    mapped = [str(Path(m["Destination"]) / socket.resolve().relative_to(Path(m["Source"])))
              for m in info["Mounts"] if socket.resolve().is_relative_to(Path(m["Source"]))]
    if len(mapped) != 1 or not socket.is_socket():
        raise ValueError("Native socket must be in the verified simulation container bind mount")
    listener = str(Path(process["args"][0]).with_name("px4-listener"))
    status = command("docker", "exec", "--user", str(socket.stat().st_uid), container, listener, "--instance", str(instance),
                     "fixed_wing_guidance_status", "-n", "1")
    uid = re.search(r"autopilot_uid:\s*(\d+)", status)
    if uid is None:
        raise ValueError("Simulator aircraft UID is unavailable")
    return dict(container_id=info["Id"], image_id=info["Image"], instance=instance,
                process=process, aircraft_uid=uid.group(1), native_socket=mapped[0],
                initial_native_status=status)


def stable_window(states: list[AircraftState], *, minimum_relative_altitude_m=15., expected_altitude_m=None) -> bool:
    if len(states) < 7:
        return False
    phase = states[0].phase
    if phase not in (AirframePhase.FIXED_WING, AirframePhase.MULTICOPTER):
        return False
    if any(s.phase is not phase or s.rescue_active or s.fixed_wing_envelope is None
           or s.relative_altitude_m < minimum_relative_altitude_m for s in states):
        return False
    if phase is AirframePhase.FIXED_WING and any(
            not s.airspeed.valid or s.airspeed.equivalent_m_s is None
            or s.airspeed.equivalent_m_s < s.fixed_wing_envelope.minimum_eas_m_s for s in states):
        return False
    if phase is AirframePhase.MULTICOPTER and any(
            not s.is_vtol or s.velocity_ned_m_s.horizontal_magnitude > .5
            or abs(math.remainder(s.navigation_heading_rad - states[0].navigation_heading_rad, 2 * math.pi)) > math.radians(5)
            for s in states):
        return False
    if states[-1].observed_at_monotonic_s - states[0].observed_at_monotonic_s < 2.9:
        return False
    return (max(s.relative_altitude_m for s in states) - min(s.relative_altitude_m for s in states) <= 1.
            and all(abs(s.velocity_ned_m_s.z) <= .5 for s in states)
            and (expected_altitude_m is None or all(abs(s.relative_altitude_m - expected_altitude_m) <= 2.
                                                   for s in states)))


class ObservationConnection:
    """Test-only telemetry bridge; all guidance and publication stay in production."""

    is_command_preview = False

    def __init__(self, binding):
        self.owner = AircraftStateOwner()
        self.owner.bind(binding)
        self.last_packet = None

    def get_aircraft_state(self):
        return self.owner.snapshot(timeout_s=.75)

    def commit_aircraft_state(self, state):
        return self.owner.commit(state)

    @property
    def current_altitude(self):
        state = self.get_aircraft_state()
        return None if state is None else state.relative_altitude_m


def tracker_for_world_target(packet, target, mount, *, clock=time.monotonic):
    pose = packet["vehicle_pose"]
    measured_at = pose["observed_at_monotonic_s"]
    if not 0. <= clock() - measured_at <= .5:
        raise ValueError("px4_pose_stale")
    angles = camera_angles_for_world_target(pose["vehicle_ned"], target, pose["quaternion_wxyz"], mount)
    return TrackerOutput(TrackerDataType.GIMBAL_ANGLES, time.time(), True,
                         tracker_id="independent_sih_target", angular=angles,
                         raw_data={"angle_sample_monotonic": measured_at, "has_output": True,
                                   "usable_for_following": True, "data_is_stale": False},
                         metadata={"guidance_capabilities": dict(known=True, supports_vertical=True,
                                   supports_reverse=True, supports_yaw_fallback=True)})


async def run(args, isolation):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    for directory in ("trace", "px4"):
        (output / directory).mkdir()
    config = yaml.safe_load(args.config.read_text())
    config["GimbalTracker"]["MOUNT_TYPE"] = args.mount
    config["Follower"]["FollowerOverrides"].setdefault("GM_VELOCITY_VECTOR", {})["ENABLE_ALTITUDE_CONTROL"] = args.altitude
    # Explicit simulator overlay; public and installed configurations stay untouched.
    config["Follower"]["FOLLOWER_MODE"] = "gm_velocity_vector"
    config["FOLLOWER_CIRCUIT_BREAKER"] = False
    (output / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    Parameters.load_config(output / "config.yaml", strict_dependents=True)
    source = command("git", "-C", str(ROOT), "rev-parse", "HEAD").strip()
    patch = command("git", "-C", str(ROOT), "diff", "HEAD")
    (output / "source.patch").write_text(patch)
    (output / "manifest.json").write_text(json.dumps(dict(
        evidence_kind="px4_observed_sih", qualification="native_vector_component",
        application_startup_qualified=False, revision=source, worktree_dirty=bool(patch),
        isolation=isolation, altitude_guidance=args.altitude, mount=args.mount,
    ), indent=2))
    logs = {}

    def log(name, value):
        if name not in logs:
            logs[name] = (output / name).open("x")
        logs[name].write(json.dumps(value, allow_nan=False) + "\n")
        logs[name].flush()

    client = NativeGuidanceClient(args.socket)
    commander = binding = None
    result = dict(passed=False, reason="not_started")
    started = time.monotonic()
    try:
        capabilities = await client.connect()
        aircraft = AircraftBinding(isolation["aircraft_uid"], f"sih-{output.name}", 1)
        log("runtime.jsonl", dict(timestamp=time.monotonic(), capabilities=asdict(capabilities),
                                  binding=asdict(aircraft),
                                  control_contract="native_vector_component_only"))
        await client.bind(aircraft)
        connection = ObservationConnection(aircraft)
        window = []
        while time.monotonic() - started < args.stable_timeout:
            packet = await client.observe()
            log("observations.jsonl", dict(timestamp=time.monotonic() - started, value=packet))
            # PX4 VehicleStatus::NAVIGATION_STATE_AUTO_LOITER. Takeoff/landing
            # transients cannot satisfy a numerically flat altitude window.
            if (packet["fresh"] and not packet["rescue_active"] and packet.get("vehicle_pose")
                    and packet.get("nav_state") == 4):
                state = AircraftState.from_payload(packet["aircraft_state"])
                connection.commit_aircraft_state(state)
                connection.last_packet = packet
                if not window or state.sequence > window[-1].sequence:
                    window = (window + [state])[-7:]
                if stable_window(window, expected_altitude_m=args.test_altitude):
                    break
            else:
                window = []
            await asyncio.sleep(.5)
        else:
            raise ValueError("stable_airborne_window_not_reached")
        log("stable-flight.jsonl", dict(timestamp=time.monotonic() - started, states=[asdict(s) for s in window]))
        follower = FollowerFactory.create_follower("gm_velocity_vector", connection, (.5, .5))
        guidance = follower.create_airframe_session(
            GuidanceSessionIdentity(output.name, aircraft, 1), capabilities,
            confirmation_s=config["Follower"]["AIRFRAME_PHASE_CONFIRMATION_S"],
            observation_timeout_s=.75, transition_timeout_s=config["Follower"]["VTOL_TRANSITION_TIMEOUT_S"],
            fixed_wing_policy=FixedWingGuidancePolicy.from_mapping(config["FixedWingGuidance"]),
        )
        continuity_config = config["TargetContinuity"]
        supervisor = TargetContinuitySupervisor(ContinuityPolicy.resolve(
            continuity_config, "gm_velocity_vector", state.phase))
        supervisor.reset_session(session_epoch=1, reason="isolated_sih_start")
        target_output = [None]

        def target_evidence():
            return TargetEvidenceSnapshot.from_tracker_output(target_output[0], session_epoch=1)

        base = ContinuityContext("PX4_NATIVE", state.phase, "fixed_wing_external", True, False, True)
        binding = NativeFollowBinding(
            guidance, connection, client, supervisor, profile_name="gm_velocity_vector",
            continuity_config=continuity_config, target_evidence=target_evidence, context=lambda: base,
            circuit_breaker=lambda: False,
        )
        original_observer = binding.transport.on_observation

        async def observation(state, packet, intent):
            connection.last_packet = packet
            log("observations.jsonl", dict(timestamp=time.monotonic() - started, value=packet))
            return await original_observer(state, packet, intent)

        binding.transport.on_observation = observation
        pose = connection.last_packet["vehicle_pose"]
        origin = pose["vehicle_ned"]
        heading = state.navigation_heading_rad
        forward, right = (math.cos(heading), math.sin(heading)), (-math.sin(heading), math.cos(heading))
        # Fixed world trajectory, frozen before following. Never moved relative to the chasing aircraft.
        target_start = [origin[k] + forward[k] * 160. + right[k] * 35. for k in (0, 1)]
        target_start.append(origin[2] + (8. if args.altitude else 0.))
        target_end = [target_start[k] + forward[k] * 6. * args.duration for k in (0, 1)] + [target_start[2]]
        scenario_raw = yaml.safe_load((ROOT / "tools/sih_visualization_scenarios/gimbal-vector-native-fw.yaml").read_text())
        scenario_raw.update(name=output.name, mount_type=args.mount, initial_conditions={"vehicle_ned": origin})
        if state.is_vtol:
            scenario_raw["airframe"] = "vtol"
            scenario_raw["follower"]["command_contract"] = "vtol_external"
        scenario_raw["follower"]["altitude_control"] = args.altitude
        scenario_raw["target"]["waypoints"] = [dict(time_s=0., position_ned=target_start),
                                                dict(time_s=args.duration, position_ned=target_end)]
        scenario_path = output / "scenario.yaml"
        scenario_path.write_text(yaml.safe_dump(scenario_raw, sort_keys=False))
        scenario = VisualizationScenario.from_yaml(scenario_path)

        target_output[0] = tracker_for_world_target(connection.last_packet, target_start, args.mount)
        baseline = await binding.engage()
        follower.bind_airframe_session(guidance)

        async def published(event):
            intent = event["command_intent"]
            log("trace/offboard_publish_trace.jsonl", dict(
                record_type="offboard_publish", timestamp=time.monotonic() - follow_start,
                publish_success=event["publish_status"]["last_publish_success"],
                command_intent=None if intent is None else asdict(intent)))

        commander = OffboardCommander(connection, follower.setpoint_handler, command_rate_hz=20.,
                                      command_ttl_s=.3, command_transport=binding.transport,
                                      on_publish_result=published)
        if not commander.submit_intent(baseline):
            raise ValueError(commander.last_error)
        follow_start = time.monotonic()
        if not await commander.start():
            raise ValueError(commander.last_error)
        initial_altitude = state.relative_altitude_m
        initial_publications = commander.successful_publishes
        response = []
        mc_request_applied = False
        while (elapsed := time.monotonic() - follow_start) < args.duration:
            packet = connection.last_packet
            state = connection.get_aircraft_state()
            if state is None or not commander.running or commander.failed_publishes:
                raise ValueError("native_publication_or_state_unhealthy")
            if (args.mc_request is not None and not mc_request_applied and not binding.pursuit_paused
                    and state.phase is AirframePhase.MULTICOPTER):
                control = guidance.controls.current_control
                follower.update_session_control("requested_speed", args.mc_request, control.revision)
                mc_request_applied = True
                log("session-control-updates.jsonl", dict(timestamp=elapsed, control="requested_speed",
                    value=args.mc_request, guidance_identity=asdict(guidance.identity)))
            target = scenario.target_at(elapsed)
            pose_time = max(0., packet["vehicle_pose"]["observed_at_monotonic_s"] - follow_start)
            measurement_target = scenario.target_at(pose_time)
            target_output[0] = tracker_for_world_target(packet, measurement_target, args.mount)
            nominal = binding.paused_baseline()
            if nominal is None:
                if not follower.follow_target(target_output[0]):
                    raise ValueError(f"follower_refused:{follower._safety_rejection}")
                nominal = follower.get_last_command_intent()
            decision = supervisor.evaluate(target_evidence(), binding.context(base), nominal)
            if decision.handoff_request is not None:
                raise ValueError(f"continuity_handoff:{decision.reason_code}")
            intent = decision.authorized_intent
            fields = follower.limit_session_control_command(dict(intent.fields))
            fields = follower.limit_authorized_command(fields)
            intent = replace(intent, fields=fields)
            if not commander.submit_intent(intent):
                raise ValueError(commander.last_error)
            supervisor.record_authorized_intent(intent)
            follower.record_submitted_command(fields)
            feedback = packet.get("native_guidance_feedback") or {}
            p = packet["vehicle_pose"]
            response.append(dict(range_m=math.dist(p["vehicle_ned"], target),
                                 altitude_m=state.relative_altitude_m,
                                 eas_m_s=state.airspeed.equivalent_m_s,
                                 pose_observed_at=p["observed_at_monotonic_s"]))
            log("px4/pose_trace.jsonl", dict(timestamp=elapsed, vehicle_ned=p["vehicle_ned"],
                vehicle_quaternion=p["quaternion_wxyz"], px4_timestamp_us=p["px4_timestamp_us"],
                native_fw_forward_ned=feedback.get("fixed_wing_forward_ned"), source=p["source"]))
            log("trace/target_truth.jsonl", dict(timestamp=elapsed, target_ned=target))
            log("trace/tracker_command_trace.jsonl", dict(record_type="tracker_command", timestamp=elapsed,
                requested_speed=(guidance.controls.current_control.value if guidance.controls.current_control else None),
                command_intent=asdict(intent),
                measurement_age_s=time.monotonic() - target_output[0].raw_data["angle_sample_monotonic"],
                measurement_target_ned=measurement_target,
                tracker_output=target_output[0].to_dict()))
            log("trace/follower_state.jsonl", dict(timestamp=elapsed, state=decision.authority_state.value,
                aircraft_phase=state.phase.value, observed_eas_m_s=state.airspeed.equivalent_m_s,
                native_effective_eas_m_s=feedback.get("effective_eas_m_s")))
            await asyncio.sleep(.05)
        await commander.stop(publish_final=False)
        native_publications = binding.transport.observed_publications
        handoff = await binding.stop("isolated_sih_complete")
        await client.connect()
        await client.bind(aircraft)
        packet = await client.observe()
        log("final-observation.jsonl", packet)
        after_stop = []
        for _ in range(5):
            await asyncio.sleep(.1)
            stopped_packet = await client.observe()
            after_stop.append(stopped_packet["publications"])
            log("post-stop-observations.jsonl", stopped_packet)
        altitude_error = max(abs(row["altitude_m"] - initial_altitude) for row in response)
        checks = dict(range_decreased=response[-1]["range_m"] < response[0]["range_m"],
                      altitude_floor=min(row["altitude_m"] for row in response) >= follower.altitude_limits.min_altitude,
                      finite_observed_response=all(math.isfinite(row["range_m"]) for row in response),
                      no_publication_after_stop=len(set(after_stop + [packet["publications"]])) == 1,
                      hold_confirmed=handoff["executed"],
                      no_publication_failure=commander.failed_publishes == 0)
        if args.altitude:
            checks["altitude_guidance_response"] = response[-1]["altitude_m"] < initial_altitude - .5
        else:
            checks["altitude_hold"] = altitude_error <= args.altitude_tolerance
        result = dict(passed=all(checks.values()), reason="component_scenario_complete", response_checks=checks,
                      scope="native_vector_component_only", handoff=handoff,
                      successful_publications=commander.successful_publishes - initial_publications,
                      observed_native_publications=native_publications,
                      failed_publications=commander.failed_publishes, initial_relative_altitude_m=initial_altitude,
                      final_relative_altitude_m=packet["aircraft_state"]["relative_altitude_m"],
                      target_range_start_m=response[0]["range_m"], target_range_end_m=response[-1]["range_m"],
                      maximum_altitude_change_m=altitude_error,
                      maximum_altitude_hold_error_m=None if args.altitude else altitude_error,
                      required_altitude_hold_tolerance_m=None if args.altitude else args.altitude_tolerance,
                      application_startup_qualified=False)
    except Exception as error:
        result = dict(passed=False, reason=f"{type(error).__name__}:{error}")
        raise
    finally:
        if commander is not None and commander.running:
            await commander.stop(publish_final=False)
        if binding is not None and binding.owner_confirmed:
            try:
                result["cleanup"] = await binding.stop("isolated_sih_cleanup")
            except Exception as error:
                result["cleanup_error"] = str(error)
        await client.close()
        (output / "result.json").write_text(json.dumps(result, indent=2))
        for log_file in logs.values():
            log_file.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--container", required=True)
    parser.add_argument("--instance", type=int, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/config_default.yaml")
    parser.add_argument("--mount", choices=("HORIZONTAL", "VERTICAL"), required=True)
    parser.add_argument("--altitude", action="store_true")
    parser.add_argument("--duration", type=float, default=15.)
    parser.add_argument("--stable-timeout", type=float, default=90.)
    parser.add_argument("--test-altitude", type=float, default=30., help="Stable SIH altitude, home-relative metres")
    parser.add_argument("--altitude-tolerance", type=float, default=2., help="Maximum measured hold error, metres")
    parser.add_argument("--mc-request", type=float, help="Explicit simulated operator speed adjustment in initial VTOL MC")
    args = parser.parse_args()
    if not 1. <= args.duration <= 60. or not 1. <= args.stable_timeout <= 180.:
        parser.error("Scenario duration must be 1–60 s; stable timeout must be 1–180 s")
    if not 15. <= args.test_altitude <= 120. or not 0. < args.altitude_tolerance <= 10.:
        parser.error("SIH altitude must be 15–120 m; hold tolerance must be (0,10] m")
    if args.mc_request is not None and (not math.isfinite(args.mc_request) or args.mc_request < 0.):
        parser.error("MC request must be finite and nonnegative")
    isolation = verify_simulator(args.container, args.instance, args.socket)
    if not args.execute:
        print(json.dumps(dict(execute=False, isolation=isolation), indent=2))
        return
    result = asyncio.run(run(args, isolation))
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
