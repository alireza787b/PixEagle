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
from classes.fixed_wing_mavlink_control import FIXED_WING_MAVLINK_PARAMETERS, resolve_mavlink_configuration  # noqa: E402
from classes.fixed_wing_mavlink_control import FixedWingAttitudeRequest  # noqa: E402
from classes.gimbal_guidance import GimbalGuidancePolicy  # noqa: E402
from classes.mavlink_data_manager import MavlinkDataManager  # noqa: E402
from classes.mavlink_command_transport import MavlinkCommandTransport  # noqa: E402
from classes.mavlink_aircraft_state import AirspeedProgress, mode_observed_after_request  # noqa: E402
from classes.parameters import Parameters  # noqa: E402
from classes.follower_config_manager import get_follower_config_manager  # noqa: E402
from classes.safety_manager import get_safety_manager  # noqa: E402
from classes.stock_mavlink_setpoints import fixed_wing_attitude_packet, offboard_mode_packet, hold_mode_packet, PX4_HOLD_MODE  # noqa: E402
from classes.airframe_session_controls import AirframeSessionControls  # noqa: E402
from classes.mavlink_vector_guidance_session import MavlinkGuidanceCapabilities, MavlinkVectorGuidanceSession  # noqa: E402
from classes.setpoint_handler import SetpointHandler  # noqa: E402
from classes.offboard_commander import OffboardCommander  # noqa: E402
from classes.px4_interface_manager import PX4InterfaceManager  # noqa: E402
try:
    from tools.mc_follower_sih import PoseProgress, pose_observation, request_telemetry_identity
except ModuleNotFoundError:
    from mc_follower_sih import PoseProgress, pose_observation, request_telemetry_identity


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


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
    telemetry = MavlinkDataManager("127.0.0.1", 8088, .1, Parameters.MAVLINK_DATA_POINTS)
    telemetry.start_polling()
    progress = PoseProgress()
    source_epoch = None
    timeout = telemetry.stale_timeout_s
    names = (*FIXED_WING_MAVLINK_PARAMETERS, "COM_OF_LOSS_T")
    parameters = {name: await drone.param.get_param_float(name) for name in names}
    parameters["COM_OBL_RC_ACT"] = await drone.param.get_param_int("COM_OBL_RC_ACT")
    write_json(output / "px4-parameters.json", parameters)
    await asyncio.to_thread(request_telemetry_identity, requests)
    envelope, tuning = resolve_mavlink_configuration(parameters,
        revision=manifest["sih_baseline"]["firmware"]["commit"], lookahead_m=Parameters.FW_ATTITUDE_RATE["L1_DISTANCE"])
    binding = AircraftBinding(uid, "isolated-stock-mavsdk-1", 1)
    guidance_identity = GuidanceSessionIdentity(os.environ["EVIDENCE_OWNER"], binding, 1)
    controller = FixedWingMavlinkVectorControl(
        tuning=tuning, geometry=GimbalGuidancePolicy().geometry,
        policy=policy,
        enable_altitude_control=get_follower_config_manager().get_param("ENABLE_ALTITUDE_CONTROL", "GM_VELOCITY_VECTOR"),
    )
    limits = get_safety_manager().get_altitude_limits("GM_VELOCITY_VECTOR")
    observations = []
    active = False
    stop_attempted = False
    session = None
    owner = None
    commander = None

    async def snapshot():
        nonlocal source_epoch
        payload = await asyncio.to_thread(lambda: requests.get("http://127.0.0.1:8088/v1/mavlink", timeout=2).json())
        flight = telemetry.get_flight_state()
        if (not flight.get("phase_observation", {}).get("fresh")
                or flight["phase_observation"]["phase"] != "fixed_wing"):
            raise RuntimeError("Fresh stock fixed-wing phase required")
        sample = pose_observation(payload, flight, None, expected_aircraft_uid=uid)
        progress.accept(sample["source_boot_ms"], clock())
        if source_epoch is None:
            source_epoch = telemetry.get_aircraft_state_source_epoch()
        state = telemetry.get_aircraft_state_observation(binding, source_epoch=source_epoch, envelope=envelope)
        if state is None:
            raise RuntimeError("Source-owned stock aircraft observation unavailable")
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
        if args.session:
            step = SetpointHandler.get_profile_info("gm_velocity_vector")["session_controls"]["requested_speed"]["step"]
            session = MavlinkVectorGuidanceSession(guidance_identity,
                MavlinkGuidanceCapabilities(os.environ["EVIDENCE_OWNER"], True, False, False, unconstrained),
                projection=controller, profile_name="gm_velocity_vector",
                controls=AirframeSessionControls.for_fixed_wing(guidance_identity, step_m_s=step),
                supported_phases=frozenset({AirframePhase.FIXED_WING}), geometry_policy=GimbalGuidancePolicy().geometry,
                altitude_control=controller.direction.enable_altitude_control, altitude_limits=limits,
                confirmation_s=Parameters.AIRFRAME_PHASE_CONFIRMATION_S, observation_timeout_s=timeout,
                clock=clock, fixed_wing_policy=policy, initial_phase=AirframePhase.FIXED_WING)
            session.prepare_engagement_reference(state)
        else:
            controller.begin(guidance_identity, state, now=clock(), timeout_s=timeout)
        heading = state.navigation_heading_rad
        north, east, down = sample["position_ned"]
        drop = args.target_down_m if args.target_down_m is not None else (50. if unconstrained else 0.)
        anchor = Vector3(north + args.target_forward_m * math.cos(heading) - 40 * math.sin(heading),
                         east + args.target_forward_m * math.sin(heading) + 40 * math.cos(heading),
                         down + drop)
        target_velocity = Vector3(4 * math.cos(heading), 4 * math.sin(heading), 0.)
        write_json(output / "target-definition.json", {"anchor_ned": asdict(anchor),
                    "velocity_ned_m_s": asdict(target_velocity), "source": "independent_constant_velocity_world_target"})
        initial_request = max(envelope.minimum_eas_m_s, controller.speed_feedback(state, now=clock(), timeout_s=timeout)[0])
        if args.owner:
            commander = OffboardCommander(None, SetpointHandler("gm_velocity_vector"))
            async def send(packet):
                await drone.mavlink_direct.send_message(packet.sdk_message())
            owner = MavlinkCommandTransport(session,
                observe=lambda: telemetry.get_guidance_observation(binding, source_epoch=source_epoch, envelope=envelope),
                send=send, owns_session=lambda: telemetry.get_aircraft_state_source_epoch() == source_epoch,
                target_confirmed=lambda: True, circuit_breaker=lambda: False,
                command_period_s=commander.command_period_s, prime_duration_s=PX4InterfaceManager.OFFBOARD_PRIME_DURATION_S,
                command_timeout_s=Parameters.MAVSDK_COMMAND_TIMEOUT_S)
            commander.command_transport = owner
            await owner.engage(before_dispatch=lambda: None)
        elif args.direct:
            neutral = FixedWingAttitudeRequest(sample["roll_deg"], sample["pitch_deg"], math.degrees(heading),
                parameters["FW_THR_TRIM"], initial_request, initial_request, initial_request, "priming", "baseline", None)
            for _ in range(25):
                await drone.mavlink_direct.send_message(fixed_wing_attitude_packet(
                    neutral, now=clock(), system_id=telemetry.system_id, component_id=telemetry.component_id).sdk_message())
                await asyncio.sleep(.05)
        else:
            await drone.offboard.set_attitude(Attitude(sample["roll_deg"], sample["pitch_deg"],
                                                     math.degrees(heading), parameters["FW_THR_TRIM"]))
            await asyncio.sleep(1.2)
        # Warm-up is a neutral flight baseline, not a retained target command.
        await snapshot()
        if args.direct and not args.owner:
            mode_requested_at = clock()
            await drone.mavlink_direct.send_message(offboard_mode_packet(
                system_id=telemetry.system_id, component_id=telemetry.component_id).sdk_message())
            deadline = clock() + Parameters.MAVSDK_COMMAND_TIMEOUT_S
            while not mode_observed_after_request(telemetry.get_flight_state(), source_epoch=source_epoch,
                    expected_mode=telemetry.offboard_mode_code, requested_at=mode_requested_at):
                if clock() >= deadline:
                    raise RuntimeError("stock_offboard_mode_confirmation_timeout")
                if telemetry.get_aircraft_state_source_epoch() != source_epoch:
                    raise RuntimeError("stock_start_source_epoch_changed")
                await drone.mavlink_direct.send_message(fixed_wing_attitude_packet(
                    neutral, now=clock(), system_id=telemetry.system_id, component_id=telemetry.component_id).sdk_message())
                await asyncio.sleep(.05)
        elif not args.owner:
            await drone.offboard.start()
        active = True
        started = clock()
        adjusted = False
        restored = False
        while clock() - started < 20.:
            loop_started = clock()
            elapsed = loop_started - started
            sample, state = await snapshot()
            target = Vector3(anchor.x + target_velocity.x * elapsed, anchor.y + target_velocity.y * elapsed, anchor.z)
            ray = Vector3(target.x - sample["position_ned"][0], target.y - sample["position_ned"][1],
                          target.z - sample["position_ned"][2])
            requested = initial_request if elapsed < 8. else envelope.maximum_eas_m_s * (1.5 if unconstrained else 1.)
            if session is not None:
                decision = session.observe(state,
                    owner_confirmed=telemetry.get_flight_state().get("flight_mode") == telemetry.offboard_mode_code,
                    target_confirmed=True)
                if decision.state.value == "ended":
                    raise RuntimeError(decision.reason)
                if elapsed >= 8. and not adjusted:
                    session.controls.update(requested, identity=session.identity,
                        expected_revision=session.controls.current_control.revision)
                    adjusted = True
                if args.restore_during_session and elapsed >= 12. and not restored:
                    session.controls.update(None, identity=session.identity,
                        expected_revision=session.controls.current_control.revision)
                    restored = True
                intent = session.calculate_ned(ray.normalized(), frame="ned")
                if owner is not None:
                    if not commander.submit_intent(intent) or not await commander.publish_once(reason="component"):
                        raise RuntimeError(commander.last_error or "stock_commander_publication_failed")
                else:
                    packet = session.packet(intent, state, system_id=telemetry.system_id, component_id=telemetry.component_id)
                    await drone.mavlink_direct.send_message(packet.sdk_message())
                request = session.last_projection
            else:
                request = controller.calculate(ray, state, identity=guidance_identity, requested_speed_m_s=requested,
                                               altitude_limits=limits, now=clock(), timeout_s=timeout)
            if args.direct and session is None:
                await drone.mavlink_direct.send_message(fixed_wing_attitude_packet(
                    request, now=clock(), system_id=telemetry.system_id, component_id=telemetry.component_id).sdk_message())
            elif not args.direct:
                await drone.offboard.set_attitude(Attitude(request.roll_deg, request.pitch_deg, request.yaw_deg, request.thrust))
            row = {"timestamp": time.time(), "monotonic_s": clock(), "elapsed_s": elapsed,
                   "vehicle_ned": sample["position_ned"], "quaternion_wxyz": sample["quaternion_wxyz"],
                   "target_ned": [target.x, target.y, target.z], "range_m": ray.magnitude,
                   "relative_altitude_m": state.relative_altitude_m, "request": asdict(request),
                   "phase": state.phase.value, "source_boot_ms": sample["source_boot_ms"]}
            row["effective_upper_speed_policy"] = controller.policy.upper_speed_policy.value
            if session is not None:
                row["session_control"] = session.controls.snapshot(client_contract_version=2)
            observations.append(row)
            with (output / "observations.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            await asyncio.sleep(max(0., .05 - (clock() - loop_started)))
        if args.publication_outage:
            outage_started = clock()
            async def observe_exit():
                async for mode in drone.telemetry.flight_mode():
                    if str(mode) != "OFFBOARD":
                        return str(mode), clock() - outage_started
            mode, delay = await asyncio.wait_for(observe_exit(), timeout=parameters["COM_OF_LOSS_T"] + 3.)
            active = False  # Native failsafe owns the mode; cleanup must not replace it.
            await asyncio.sleep(1.)
            flight = telemetry.get_flight_state()
            sdk_resending = await drone.offboard.is_active()
            result = {"scope": "stock_mavlink_publication_loss_component_only",
                      "application_startup_qualified": False, "hardware_qualified": False,
                      "publication": "mavlink_direct_one_shot", "submissions_before_outage": len(observations),
                      "observed_exit_mode": mode, "offboard_exit_delay_s": delay,
                      "configured_loss_timeout_s": parameters["COM_OF_LOSS_T"],
                      "configured_loss_action": parameters["COM_OBL_RC_ACT"],
                      "mavsdk_autoresend_active_after_outage": sdk_resending,
                      "rest_flight_state_after_outage": flight,
                      "passed": (not sdk_resending and flight.get("fresh") is True
                                 and flight.get("flight_mode") != telemetry.offboard_mode_code)}
            write_json(output / "result.json", result)
            if not result["passed"]:
                raise RuntimeError("Stock publication-loss failsafe not confirmed")
            return
        if session is not None and owner is None:
            session.end("operator_stop")
        if owner is not None:
            stop_attempted = True
            if not (await owner.stop("operator_stop"))["executed"]:
                raise RuntimeError("stock_owner_hold_unconfirmed")
        elif args.direct:
            stop_requested_at = clock()
            stop_attempted = True
            await drone.mavlink_direct.send_message(hold_mode_packet(
                system_id=telemetry.system_id, component_id=telemetry.component_id).sdk_message())
            deadline = clock() + Parameters.MAVSDK_COMMAND_TIMEOUT_S
            while not mode_observed_after_request(telemetry.get_flight_state(), source_epoch=source_epoch,
                    expected_mode=PX4_HOLD_MODE, requested_at=stop_requested_at):
                if clock() >= deadline:
                    raise RuntimeError("stock_hold_mode_confirmation_timeout")
                await asyncio.sleep(.05)
        else:
            await drone.offboard.stop()
        active = False
        async for mode in drone.telemetry.flight_mode():
            if str(mode) == "HOLD":
                break
        handoff = []
        for _ in range(16):
            sample, state = await snapshot()
            speed, basis = controller.speed_feedback(state, now=clock(), timeout_s=timeout)
            row = {"timestamp": time.time(), "monotonic_s": clock(),
                   "relative_altitude_m": state.relative_altitude_m, "speed_m_s": speed,
                   "speed_basis": basis, "source_boot_ms": sample["source_boot_ms"]}
            handoff.append(row)
            with (output / "handoff.jsonl").open("a") as stream:
                stream.write(json.dumps(row) + "\n")
            await asyncio.sleep(.5)
        result = {"scope": "stock_mavlink_fw_vector_component_only", "application_startup_qualified": False,
                  "hardware_qualified": False, "unconstrained": unconstrained,
                  "publication": "mavlink_direct_one_shot" if args.direct else "mavsdk_offboard_resend",
                  "aircraft_observation": "production_mavlink_source",
                  "shared_session": session is not None,
                  "production_command_owner": owner is not None,
                  "commander_status": None if commander is None else commander.get_status(),
                  "session_speed_adjusted": adjusted,
                  "session_envelope_restored": restored,
                  "session_control_after_stop": None if session is None else session.controls.snapshot(client_contract_version=2),
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
        if args.session:
            result["passed"] = result["passed"] and adjusted and result["session_control_after_stop"] is None
        if args.restore_during_session:
            result["passed"] = result["passed"] and restored
        write_json(output / "result.json", result)
        if not result["passed"]:
            raise RuntimeError("Stock FW component response check failed")
    finally:
        if active and not stop_attempted:
            flight = telemetry.get_flight_state()
            if (flight.get("fresh") is True and flight.get("flight_mode") == telemetry.offboard_mode_code
                    and telemetry.get_aircraft_state_source_epoch() == source_epoch):
                if owner is not None:
                    await owner.stop("component_cleanup")
                elif args.direct:
                    await drone.mavlink_direct.send_message(hold_mode_packet(
                        system_id=telemetry.system_id, component_id=telemetry.component_id).sdk_message())
                else:
                    await drone.offboard.stop()
        if session is not None:
            session.end("component_finished")
        telemetry.stop_polling()
        controller.reset()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--unconstrained", action="store_true")
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--publication-outage", action="store_true")
    parser.add_argument("--session", action="store_true")
    parser.add_argument("--owner", action="store_true")
    parser.add_argument("--restore-during-session", action="store_true")
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
    if args.publication_outage and not args.direct:
        parser.error("Publication-outage qualification requires --direct; cached resending is a different contract")
    if args.session and not args.direct:
        parser.error("Shared stock session qualification requires --direct")
    if args.owner and not args.session:
        parser.error("Stock command-owner qualification requires --session --direct")
    if args.restore_during_session and not (args.session and args.unconstrained):
        parser.error("Envelope Restore qualification requires --session --unconstrained")
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
        if args.unconstrained:
            args.worker_extra_args.append("--unconstrained")
        if args.direct:
            args.worker_extra_args.append("--direct")
        if args.publication_outage:
            args.worker_extra_args.append("--publication-outage")
        if args.session:
            args.worker_extra_args.append("--session")
        if args.owner:
            args.worker_extra_args.append("--owner")
        if args.restore_during_session:
            args.worker_extra_args.append("--restore-during-session")
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
