"""Isolated native SIH harness gates; these tests never command an aircraft."""

from dataclasses import replace
import json
import socket

import pytest
import yaml

from classes.aircraft_state import AirframePhase
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tools.run_native_vector_sih import load_component_scenario, phase_response_segments, stable_window, tracker_for_world_target, verify_simulator


def flight_window():
    sample = aircraft_state(phase=AirframePhase.FIXED_WING, is_vtol=False, is_tailsitter=False)
    return [replace(sample, observed_at_monotonic_s=100. + n * .5, sequence=n,
                    relative_altitude_m=30., velocity_ned_m_s=replace(sample.velocity_ned_m_s, z=0.))
            for n in range(7)]


def test_fw_stable_gate_requires_seven_consecutive_airborne_native_samples():
    states = flight_window()
    assert stable_window(states)
    assert not stable_window(states[:-1])
    assert not stable_window([replace(s, observed_at_monotonic_s=100. + n * .01)
                              for n, s in enumerate(states)])


@pytest.mark.parametrize("changes", [
    {"relative_altitude_m": .1}, {"phase": AirframePhase.VTOL_TRANSITION, "is_vtol": True}, {"rescue_active": True},
    {"fixed_wing_envelope": None},
])
def test_native_gate_never_substitutes_for_ground_or_rescue_readiness(changes):
    states = flight_window()
    states[-1] = replace(states[-1], **changes)
    assert not stable_window(states)


def test_fw_stable_gate_rejects_underspeed_climb_and_altitude_excursions():
    states = flight_window()
    for state in (replace(states[-1], airspeed=replace(states[-1].airspeed, equivalent_m_s=1.)),
                  replace(states[-1], velocity_ned_m_s=replace(states[-1].velocity_ned_m_s, z=-3.)),
                  replace(states[-1], relative_altitude_m=35.)):
        assert not stable_window(states[:-1] + [state])


def test_stable_flight_cannot_complete_on_the_way_to_the_selected_test_altitude():
    states = flight_window()
    assert stable_window(states, expected_altitude_m=30.)
    assert not stable_window(states, expected_altitude_m=50.)


@pytest.mark.parametrize("mount", ["HORIZONTAL", "VERTICAL"])
def test_world_target_input_preserves_actual_pose_sample_time(mount):
    packet = {"vehicle_pose": {"vehicle_ned": [0., 0., -30.], "quaternion_wxyz": [1., 0., 0., 0.],
                               "observed_at_monotonic_s": 99.8}}
    tracker = tracker_for_world_target(packet, [50., 5., -20.], mount, clock=lambda: 100.)
    assert tracker.raw_data["angle_sample_monotonic"] == 99.8
    assert tracker.raw_data["usable_for_following"] is True
    with pytest.raises(ValueError, match="pose_stale"):
        tracker_for_world_target(packet, [50., 5., -20.], mount, clock=lambda: 101.)
    with pytest.raises(ValueError, match="pose_stale"):
        tracker_for_world_target(packet, [50., 5., -20.], mount, clock=lambda: 99.)


def test_vtol_mc_stable_gate_uses_hover_telemetry_without_fw_airspeed():
    from classes.aircraft_state import Vector3
    states = [replace(s, phase=AirframePhase.MULTICOPTER, is_vtol=True,
                      velocity_ned_m_s=Vector3(0., 0., 0.), airspeed=replace(s.airspeed, valid=False))
              for s in flight_window()]
    assert stable_window(states, expected_altitude_m=30.)
    assert not stable_window(states[:-1] + [replace(states[-1], navigation_heading_rad=1.)])
    assert not stable_window(states[:-1] + [replace(states[-1], velocity_ned_m_s=Vector3(1., 0., 0.))])
    assert not stable_window([replace(s, is_vtol=False) for s in states])


def test_component_world_target_is_not_reanchored_to_the_aircraft(tmp_path):
    from tools.run_native_vector_sih import ROOT
    raw = yaml.safe_load((ROOT / "tools/sih_visualization_scenarios/gimbal-vector-native-fw.yaml").read_text())
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw))
    loaded = load_component_scenario(path, mount="VERTICAL", altitude=False, duration=20., is_vtol=False)
    assert loaded["target"] == raw["target"]
    for changes in ({"mount": "HORIZONTAL"}, {"altitude": True}, {"duration": 60.}, {"is_vtol": True}):
        kwargs = dict(mount="VERTICAL", altitude=False, duration=20., is_vtol=False) | changes
        with pytest.raises(ValueError, match="scenario_contract_mismatch|target_does_not_cover_run"):
            load_component_scenario(path, **kwargs)
    raw["faults"] = [{"type": "loss", "start_s": 1., "end_s": 2.}]
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="fault_injection_not_implemented"):
        load_component_scenario(path, mount="VERTICAL", altitude=False, duration=20., is_vtol=False)


def test_phase_analysis_keeps_separate_repeated_mc_spans_and_actual_range_divergence():
    rows = [dict(timestamp=t, phase=phase, range_m=distance, altitude_m=altitude)
            for t, phase, distance, altitude in [(0., "multicopter", 100., 30.),
                                                (1., "multicopter", 105., 30.1),
                                                (2., "vtol_transition", 106., 29.),
                                                (3., "fixed_wing", 90., 28.),
                                                (4., "multicopter", 95., 29.)]]
    spans = phase_response_segments(rows)
    assert [s["phase"] for s in spans] == ["multicopter", "vtol_transition", "fixed_wing", "multicopter"]
    assert spans[0]["range_end_m"] > spans[0]["range_start_m"]
    assert spans[0]["altitude_max_m"] == 30.1
    assert spans[0]["samples"] == 2
    assert spans[-1]["start_s"] == 4.


@pytest.mark.parametrize("unsafe", ["host_network", "privileged", "devices", "ports", None])
def test_simulator_isolation_is_checked_before_control(monkeypatch, tmp_path, unsafe):
    path = tmp_path / "native.sock"
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(path))
    inspect = {
        "Id": "container-id", "Image": "sha256:test-image",
        "HostConfig": {"NetworkMode": "bridge", "Privileged": False, "Devices": []},
        "NetworkSettings": {"Ports": {}},
        "Mounts": [{"Source": str(tmp_path), "Destination": "/sih"}],
    }
    if unsafe == "host_network":
        inspect["HostConfig"]["NetworkMode"] = "host"
    if unsafe == "privileged":
        inspect["HostConfig"]["Privileged"] = True
    if unsafe == "devices":
        inspect["HostConfig"]["Devices"] = [{"PathOnHost": "/dev/ttyUSB0"}]
    if unsafe == "ports":
        inspect["NetworkSettings"]["Ports"] = {"14550/udp": []}
    calls = []

    def read_command(*args):
        calls.append(args)
        if args[1] == "inspect":
            return json.dumps([inspect])
        if "python3" in args:
            return json.dumps([dict(args=["/src/build/px4_sitl_sih/bin/px4", "-i", "7"],
                                    model="sihsim_airplane", cwd="/sih/rootfs")])
        return "autopilot_uid: 123456789\n"

    monkeypatch.setattr("tools.run_native_vector_sih.command", read_command)
    try:
        if unsafe:
            with pytest.raises(ValueError, match="isolated container"):
                verify_simulator("sim", 7, path)
            assert len(calls) == 1
        else:
            info = verify_simulator("sim", 7, path)
            assert info["aircraft_uid"] == "123456789"
            assert info["native_socket"] == "/sih/native.sock"
            assert all("arm" not in call and "takeoff" not in call for call in calls)
    finally:
        listener.close()
