#!/usr/bin/env python3
"""Isolated stock-airplane component test; never an App/physical-flight pass."""

import argparse
import asyncio
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from classes.aircraft_state import (  # noqa: E402
    AircraftBinding, AircraftState, AirframePhase, AirspeedObservation,
    FixedWingEnvelope, GuidanceSessionIdentity, Quaternion, Vector3,
)
from classes.fixed_wing_guidance_policy import FixedWingGuidancePolicy, UpperSpeedPolicy  # noqa: E402
from classes.fixed_wing_mavlink_control import FixedWingMavlinkTuning, FixedWingMavlinkVectorControl  # noqa: E402
from classes.gimbal_guidance import GimbalGuidancePolicy  # noqa: E402
from classes.mavlink_data_manager import MavlinkDataManager  # noqa: E402
from classes.parameters import Parameters  # noqa: E402
from classes.follower_config_manager import get_follower_config_manager  # noqa: E402
from classes.safety_manager import get_safety_manager  # noqa: E402
try:
    from tools.mc_follower_sih import PoseProgress, pose_observation, request_telemetry_identity
except ModuleNotFoundError:
    from mc_follower_sih import PoseProgress, pose_observation, request_telemetry_identity


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


class AirspeedProgress:
    """VFR_HUD cache reads retain the advancing packet's original local clock."""

    def __init__(self):
        self.counter = None
        self.observation = None

    def observe(self, packet, now):
        try:
            counter = packet["status"]["time"]["counter"]
            value = packet["message"]["airspeed"]
            valid = (type(counter) is int and counter >= 0
                     and isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value) and value >= 0)
        except (KeyError, TypeError):
            valid = False
        if not valid or (self.counter is not None and counter < self.counter):
            self.observation = None
        elif self.counter is None:
            self.counter = counter
        elif counter > self.counter:
            self.counter = counter
            self.observation = AirspeedObservation("sensor", value, None, now, True)
        elif self.observation is not None and value != self.observation.equivalent_m_s:
            self.observation = None
        return self.observation or AirspeedObservation("unavailable", None, None, now, False)


def configure_component(config, *, unconstrained):
    """Isolated fixture only; saved public/private installations are untouched."""
    config["FixedWingGuidance"]["UPPER_SPEED_POLICY"] = (
        "no_upper_speed_bound" if unconstrained else "px4_configured_max")
    config["Follower"]["FollowerOverrides"]["GM_VELOCITY_VECTOR"]["ENABLE_ALTITUDE_CONTROL"] = unconstrained
    if unconstrained:
        # Null means no application ceiling only at the canonical global leaf.
        config["Safety"]["GlobalLimits"].update(MIN_ALTITUDE=3., MAX_ALTITUDE=None)
        overrides = config["Safety"]["FollowerOverrides"].get("GM_VELOCITY_VECTOR", {})
        overrides.pop("MIN_ALTITUDE", None)
        overrides.pop("MAX_ALTITUDE", None)


async def worker(args):
    import requests
    from mavsdk_grpc import System
    from mavsdk_grpc.offboard import Attitude

    output = Path("/work/evidence")
    manifest = json.loads((output / "manifest.json").read_text())
    if (not os.environ.get("EVIDENCE_OWNER") or manifest.get("network") != "none"
            or manifest.get("simulator_model") != "sihsim_airplane"
            or manifest.get("sih_baseline", {}).get("firmware", {}).get("policy") != "stock"):
        raise RuntimeError("Stock isolated SIH ownership required")
    clock = time.monotonic
    policy = FixedWingGuidancePolicy.from_mapping(Parameters.FixedWingGuidance)
    unconstrained = policy.upper_speed_policy is UpperSpeedPolicy.NO_UPPER_SPEED_BOUND
    drone = System(mavsdk_server_address="127.0.0.1", port=50051)
    await drone.connect()
    async for status in drone.core.connection_state():
        if status.is_connected:
            break
    identity = await drone.info.get_identification()
    uid = str(identity.legacy_uid)
    telemetry = MavlinkDataManager("127.0.0.1", 8088, .1, {
        "flight_mode": "/vehicles/1/components/1/messages/HEARTBEAT/message/custom_mode",
        "arm_status": "/vehicles/1/components/1/messages/HEARTBEAT/message/base_mode/bits",
    })
    telemetry.start_polling()
    progress = PoseProgress()
    airspeed_progress = AirspeedProgress()
    names = ("FW_AIRSPD_MIN", "FW_AIRSPD_TRIM", "FW_AIRSPD_MAX", "FW_THR_MIN", "FW_THR_TRIM",
             "FW_THR_MAX", "FW_P_LIM_MIN", "FW_P_LIM_MAX", "FW_R_LIM", "FW_T_CLMB_R_SP",
             "FW_T_SINK_R_SP", "FW_T_VERT_ACC", "FW_T_ALT_TC")
    parameters = {name: await drone.param.get_param_float(name) for name in names}
    write_json(output / "px4-parameters.json", parameters)
    await asyncio.to_thread(request_telemetry_identity, requests)
    envelope = FixedWingEnvelope(
        parameters["FW_AIRSPD_MIN"], parameters["FW_AIRSPD_TRIM"], parameters["FW_AIRSPD_MAX"],
        parameters["FW_T_CLMB_R_SP"], parameters["FW_T_SINK_R_SP"], math.radians(parameters["FW_R_LIM"]),
        "stock_px4_parameters", manifest["sih_baseline"]["firmware"]["commit"],
        parameters["FW_T_VERT_ACC"], parameters["FW_T_ALT_TC"],
    )
    binding = AircraftBinding(uid, "isolated-stock-mavsdk-1", 1)
    guidance_identity = GuidanceSessionIdentity(os.environ["EVIDENCE_OWNER"], binding, 1)
    controller = FixedWingMavlinkVectorControl(
        tuning=FixedWingMavlinkTuning(
            Parameters.FW_ATTITUDE_RATE["L1_DISTANCE"], 1. / parameters["FW_AIRSPD_TRIM"], parameters["FW_THR_MIN"], parameters["FW_THR_TRIM"],
            parameters["FW_THR_MAX"], math.radians(parameters["FW_P_LIM_MIN"]),
            math.radians(parameters["FW_P_LIM_MAX"]), parameters["FW_T_ALT_TC"],
        ), geometry=GimbalGuidancePolicy().geometry,
        policy=policy,
        enable_altitude_control=get_follower_config_manager().get_param("ENABLE_ALTITUDE_CONTROL", "GM_VELOCITY_VECTOR"),
    )
    limits = get_safety_manager().get_altitude_limits("GM_VELOCITY_VECTOR")
    observations = []
    active = False

    async def snapshot():
        payload = await asyncio.to_thread(lambda: requests.get("http://127.0.0.1:8088/v1/mavlink", timeout=2).json())
        flight = telemetry.get_flight_state()
        if (not flight.get("phase_observation", {}).get("fresh")
                or flight["phase_observation"]["phase"] != "fixed_wing"):
            raise RuntimeError("Fresh stock fixed-wing phase required")
        sample = pose_observation(payload, flight, None, expected_aircraft_uid=uid)
        progress.accept(sample["source_boot_ms"], clock())
        messages = payload["vehicles"]["1"]["components"]["1"]["messages"]
        observation = airspeed_progress.observe(messages.get("VFR_HUD"), clock())
        state = AircraftState(binding, sample["source_boot_ms"][0], "stock_mavlink2rest", clock(),
                              AirframePhase.FIXED_WING, False, False, False,
                              Quaternion(*sample["quaternion_wxyz"]), Vector3(*sample["velocity_ned"]),
                              sample["altitude_m"], messages["GLOBAL_POSITION_INT"]["message"]["alt"] / 1000.,
                              sample["yaw_rad"], observation, envelope)
        return sample, state

    try:
        async for health in drone.telemetry.health():
            if health.is_armable:
                break
        takeoff = args.takeoff_altitude_m or (160. if unconstrained else 80.)
        await drone.action.set_takeoff_altitude(takeoff)
        await drone.action.arm()
        await drone.action.takeoff()
        async for position in drone.telemetry.position():
            if position.relative_altitude_m > takeoff - 15.:
                break
        await drone.action.hold()
        await asyncio.sleep(8)
        sample, state = await snapshot()
        controller.begin(guidance_identity, state, now=clock(), timeout_s=.5)
        heading = state.navigation_heading_rad
        north, east, down = sample["position_ned"]
        drop = args.target_down_m if args.target_down_m is not None else (50. if unconstrained else 0.)
        anchor = Vector3(north + args.target_forward_m * math.cos(heading) - 40 * math.sin(heading),
                         east + args.target_forward_m * math.sin(heading) + 40 * math.cos(heading),
                         down + drop)
        target_velocity = Vector3(4 * math.cos(heading), 4 * math.sin(heading), 0.)
        write_json(output / "target-definition.json", {"anchor_ned": asdict(anchor),
                    "velocity_ned_m_s": asdict(target_velocity), "source": "independent_constant_velocity_world_target"})
        initial_request = max(envelope.minimum_eas_m_s, controller.speed_feedback(state, now=clock(), timeout_s=.5)[0])
        await drone.offboard.set_attitude(Attitude(sample["roll_deg"], sample["pitch_deg"],
                                                 math.degrees(heading), parameters["FW_THR_TRIM"]))
        await asyncio.sleep(1.2)
        # Warm-up is a neutral flight baseline, not a retained target command.
        await snapshot()
        await drone.offboard.start()
        active = True
        started = clock()
        while clock() - started < 20.:
            loop_started = clock()
            elapsed = loop_started - started
            sample, state = await snapshot()
            target = Vector3(anchor.x + target_velocity.x * elapsed, anchor.y + target_velocity.y * elapsed, anchor.z)
            ray = Vector3(target.x - sample["position_ned"][0], target.y - sample["position_ned"][1],
                          target.z - sample["position_ned"][2])
            requested = initial_request if elapsed < 8. else envelope.maximum_eas_m_s * (1.5 if unconstrained else 1.)
            request = controller.calculate(ray, state, identity=guidance_identity, requested_speed_m_s=requested,
                                           altitude_limits=limits, now=clock(), timeout_s=.5)
            await drone.offboard.set_attitude(Attitude(request.roll_deg, request.pitch_deg, request.yaw_deg, request.thrust))
            row = {"timestamp": time.time(), "monotonic_s": clock(), "elapsed_s": elapsed,
                   "vehicle_ned": sample["position_ned"], "quaternion_wxyz": sample["quaternion_wxyz"],
                   "target_ned": [target.x, target.y, target.z], "range_m": ray.magnitude,
                   "relative_altitude_m": state.relative_altitude_m, "request": asdict(request),
                   "phase": state.phase.value, "source_boot_ms": sample["source_boot_ms"]}
            observations.append(row)
            with (output / "observations.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            await asyncio.sleep(max(0., .05 - (clock() - loop_started)))
        await drone.offboard.stop()
        active = False
        async for mode in drone.telemetry.flight_mode():
            if str(mode) == "HOLD":
                break
        handoff = []
        for _ in range(16):
            sample, state = await snapshot()
            speed, basis = controller.speed_feedback(state, now=clock(), timeout_s=.5)
            row = {"timestamp": time.time(), "monotonic_s": clock(),
                   "relative_altitude_m": state.relative_altitude_m, "speed_m_s": speed,
                   "speed_basis": basis, "source_boot_ms": sample["source_boot_ms"]}
            handoff.append(row)
            with (output / "handoff.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            await asyncio.sleep(.5)
        result = {"scope": "stock_mavlink_fw_vector_component_only", "application_startup_qualified": False,
                  "hardware_qualified": False, "unconstrained": unconstrained,
                  "range_start_m": observations[0]["range_m"], "range_end_m": observations[-1]["range_m"],
                  "minimum_speed_m_s": min(row["request"]["observed_speed_m_s"] for row in observations),
                  "maximum_speed_m_s": max(row["request"]["observed_speed_m_s"] for row in observations),
                  "minimum_relative_altitude_m": min(row["relative_altitude_m"] for row in observations),
                  "post_stop_minimum_speed_m_s": min(row["speed_m_s"] for row in handoff),
                  "post_stop_minimum_relative_altitude_m": min(row["relative_altitude_m"] for row in handoff),
                  "post_stop_observation_s": handoff[-1]["monotonic_s"] - handoff[0]["monotonic_s"],
                  "hold_confirmed": True, "submissions": len(observations)}
        result["passed"] = (result["range_end_m"] < result["range_start_m"]
                            and result["minimum_speed_m_s"] >= envelope.minimum_eas_m_s
                            and result["minimum_relative_altitude_m"] >= limits.min_altitude
                            and result["post_stop_minimum_speed_m_s"] >= envelope.minimum_eas_m_s
                            and result["post_stop_minimum_relative_altitude_m"] >= limits.min_altitude)
        write_json(output / "result.json", result)
        if not result["passed"]:
            raise RuntimeError("Stock FW component response check failed")
    finally:
        if active:
            await drone.offboard.stop()
        telemetry.stop_polling()
        controller.reset()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--unconstrained", action="store_true")
    parser.add_argument("--takeoff-altitude-m", type=float)
    parser.add_argument("--target-forward-m", type=float, default=180.)
    parser.add_argument("--target-down-m", type=float)
    parser.add_argument("--follower", choices=["gm_velocity_vector"], default="gm_velocity_vector")
    parser.add_argument("--mount", choices=["HORIZONTAL", "VERTICAL"], default="VERTICAL")
    parser.add_argument("--backend-repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--simulation-build-manifest", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--bin-dir", type=Path, default=ROOT / "bin")
    parser.add_argument("--opencv-lib", type=Path, default=Path("/usr/lib/x86_64-linux-gnu"))
    args = parser.parse_args()
    if (not math.isfinite(args.target_forward_m) or args.target_forward_m <= 0
            or (args.takeoff_altitude_m is not None and (
                not math.isfinite(args.takeoff_altitude_m) or args.takeoff_altitude_m <= 30))
            or (args.target_down_m is not None and not math.isfinite(args.target_down_m))):
        parser.error("Finite target offsets, positive forward distance and takeoff altitude above 30 m required")
    if args.worker:
        asyncio.run(asyncio.wait_for(worker(args), timeout=220.))
    else:
        import shutil
        from tools.sih_isolated_host import host
        if not args.execute or args.output is None or args.simulation_build_manifest is None:
            parser.error("Explicit --execute, --output and stock --simulation-build-manifest required")
        args.simulator_model = "sihsim_airplane"
        args.evidence_kind = "stock-mavlink-fw-vector-component"
        args.worker_extra_args = ["--target-forward-m", str(args.target_forward_m)]
        for option, value in (("--target-down-m", args.target_down_m),
                              ("--takeoff-altitude-m", args.takeoff_altitude_m)):
            if value is not None:
                args.worker_extra_args.extend([option, str(value)])
        def configure(config):
            stage = args.output.resolve()
            for name in ("mc_follower_sih.py", "fixed_camera_world_target.py"):
                shutil.copyfile(args.backend_repo / "tools" / name, stage / "backend/tools" / name)
            configure_component(config, unconstrained=args.unconstrained)
        host(args, driver_path=Path(__file__), configure=configure)


if __name__ == "__main__":
    main()
