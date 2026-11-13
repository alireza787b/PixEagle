"""Canonical baseline contracts with synthetic observations; never launch a simulator."""
from dataclasses import asdict, replace
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AirframePhase, Vector3
from classes.native_guidance import NativeCapabilities
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tools import run_native_transition_baseline as tool


P, A = "a" * 64, "b" * 64


def packet(now=100., *, phase=AirframePhase.MULTICOPTER, z=-30., **changes):
    state = aircraft_state(is_vtol=True, relative_altitude_m=-z, phase=phase,
        velocity_ned_m_s=Vector3(0., 0., 0.), observed_at_monotonic_s=now,
        airspeed=replace(aircraft_state().airspeed, observed_at_monotonic_s=now))
    return dict(runtime_id="runtime", fresh=True, rescue_active=False, owner_confirmed=False,
        release_receipt=None, publications=0, release_pending=False, neutral_drain_active=False,
        nav_state=4, aircraft_state=asdict(state), vehicle_pose={"vehicle_ned": [0., 0., z]}) | changes


def args(tmp_path):
    return SimpleNamespace(output=tmp_path / "run", adapter_bundle=tmp_path / "bundle",
        adapter_file_manifest=tmp_path / "files.json", simulation_build_manifest=tmp_path / "build.json",
        build_repository=None)


def runtime(tmp_path):
    value = tool.Runtime(args(tmp_path), tool.scenario(tool.SCENARIOS / "sih-standard-hold-cycle.json"),
        "sih", {"kind": "verified_source_build", "image_id": "sha256:" + "c" * 64}, {},
        json.loads(tool.ASSETS.read_text()))
    value.primary, value.sidecar, value.created = P, A, [P, A]
    value.isolation = dict(container_id=P, image_id=value.baseline["image_id"], aircraft_uid="aircraft-a",
        process={"args": ["/opt/px4/bin/px4"], "model": "sihsim_standard_vtol"})
    return value


def info(runtime, cid):
    primary = cid == P
    mounts = [("/work", runtime.output / "simulator", True)] if primary else [
        ("/runtime", runtime.output / "simulator", True), ("/output", runtime.args.adapter_bundle, False)]
    return dict(Id=cid, Image=runtime.baseline["image_id"] if primary else runtime.assets["adapter_image"],
        Config={"User": f"{os.getuid()}:{os.getgid()}", "WorkingDir": "/work/rootfs",
                "Labels": {tool.shared.LABEL: runtime.token}},
        HostConfig={"NetworkMode": "none" if primary else "container:" + P, "Privileged": False, "Devices": []},
        NetworkSettings={"Ports": {}}, State={"Running": True},
        Mounts=[dict(Destination=dest, Source=str(source), RW=rw) for dest, source, rw in mounts])


def test_dry_run_has_no_docker_client_control_or_output_side_effect(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool.subprocess, "run", Mock(side_effect=AssertionError("process in dry run")))
    monkeypatch.setattr(tool, "NativeGuidanceClient", Mock(side_effect=AssertionError("client in dry run")))
    output = tmp_path / "absent"
    assert tool.main(["--output", str(output)]) == 0
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["execute"] is False
    with pytest.raises(SystemExit):
        tool.main(["--execute", "--output", str(output)])
    assert not output.exists()


@pytest.mark.parametrize("change", [
    {"schema_version": True}, {"model": "private_hardware"}, {"model": "sihsim_quadx"},
    {"parameters": {"MIS_TAKEOFF_ALT": 30, "FW_R_LIM": 10}},
    {"parameters": {"MIS_TAKEOFF_ALT": True}}, {"parameters": {"MIS_TAKEOFF_ALT": 10}},
    {"parameters": {"MIS_TAKEOFF_ALT": float("nan")}},
    {"parameters": {"MIS_TAKEOFF_ALT": 30, "VT_B_TRANS_DUR": True}},
    {"parameters": {"MIS_TAKEOFF_ALT": 30, "VT_B_TRANS_DUR": float("nan")}},
    {"forward": {"request_at_s": 8, "capture_s": 8}},
])
def test_fixture_cannot_select_hardware_hide_tuning_or_change_fixed_gate(tmp_path, change):
    value = tool.scenario(tool.SCENARIOS / "sih-standard-hold-cycle.json") | change
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        tool.scenario(path)
    assert tool.GATE_M == 2.


def test_slow_back_fixture_changes_only_the_explicit_native_duration():
    stock = tool.scenario(tool.SCENARIOS / "gazebo-quadtailsitter-hold-cycle.json")
    slow = tool.scenario(tool.SCENARIOS / "gazebo-quadtailsitter-slow-back-cycle.json")
    assert slow == stock | {"parameters": {"MIS_TAKEOFF_ALT": 30, "VT_B_TRANS_DUR": 10}}
    assert tool.GATE_M == 2.


@pytest.mark.parametrize("transition_parameter", ["VT_F_TRANS_DUR", "VT_B_TRANS_DUR"])
def test_boot_overlay_source_order_native_bounds_and_actual_readback(tmp_path, transition_parameter):
    import yaml
    source = tmp_path / "source"
    texts = {"ROMFS/px4fmu_common/init.d-posix/rcS":
        '"PX4_PARAM_"*) param set\n. px4-rc.simulator\ncommander start\nnavigator start\n',
        "src/modules/navigator/mission_params.yaml": yaml.safe_dump({"parameters": [{"definitions": {
            "MIS_TAKEOFF_ALT": {"min": 0}}}]}),
        "src/modules/vtol_att_control/vtol_att_control_params.yaml": yaml.safe_dump({"parameters": [{"definitions": {
            transition_parameter: {"min": .1, "max": 20}}}]}), tool.DDS_STATUS_SOURCE: "pinned status source"}
    for name, text in texts.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (source / "ROMFS/px4fmu_common/init.d-posix/airframes").mkdir()
    (source / "ROMFS/px4fmu_common/init.d-posix/airframes/10043_sihsim_standard_vtol").write_text("fixture")
    assets = {"bootstrap_files": {name: tool.digest(source / name) for name in texts}}
    fixture = tool.scenario(tool.SCENARIOS / "sih-standard-hold-cycle.json")
    fixture["parameters"][transition_parameter] = 10
    assert tool.bootstrap_contract(source, fixture, assets)["autostart"] == 10043
    tool.readback(f"MIS_TAKEOFF_ALT: 30\n{transition_parameter}: 10\n", fixture["parameters"])
    with pytest.raises(ValueError, match="readback"):
        tool.readback(f"MIS_TAKEOFF_ALT: 20\n{transition_parameter}: 10\n", fixture["parameters"])
    with pytest.raises(ValueError, match="readback"):
        tool.readback(f"MIS_TAKEOFF_ALT: 30\n{transition_parameter}: 5\n", fixture["parameters"])
    for outside_bounds in (.09, 20.01):
        with pytest.raises(ValueError, match="bounds"):
            tool.bootstrap_contract(source, fixture | {"parameters": {
                "MIS_TAKEOFF_ALT": 30, transition_parameter: outside_bounds}}, assets)
    startup = source / "ROMFS/px4fmu_common/init.d-posix/rcS"
    startup.write_text("navigator start\n" + texts[str(startup.relative_to(source))])
    with pytest.raises(ValueError, match="source changed"):
        tool.bootstrap_contract(source, fixture, assets)


@pytest.mark.parametrize("changes", [{"fresh": False}, {"rescue_active": True},
    {"aircraft_state": None}, {"vehicle_pose": None}])
def test_unusable_reply_keeps_actual_pose_for_full_window_metric(changes):
    value = packet(z=-36., **changes)
    state, z, issues = tool.sample(value, aircraft_state().binding, "runtime", 100.)
    assert state is None and issues
    assert z == (-36. if value.get("vehicle_pose") else None)


@pytest.mark.parametrize("changes", [{"owner_confirmed": True}, {"publications": 1},
    {"runtime_id": "replacement"}, {"release_pending": True}, {"neutral_drain_active": True}])
@pytest.mark.asyncio
async def test_original_reply_is_retained_before_owner_or_runtime_refusal(changes):
    value = packet(**changes)
    client = SimpleNamespace(observe=AsyncMock(return_value=value))
    stream = io.StringIO()
    with pytest.raises(ValueError, match="Native-only"):
        await tool.observe(client, aircraft_state().binding, "runtime", stream, "forward", clock=lambda: 100.)
    assert json.loads(stream.getvalue())["packet"] == value


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["stale_pose", "late_phase", "unknown", "takeover"])
async def test_real_capture_preserves_full_window_and_requires_target_phase_settle(tmp_path, monkeypatch, case):
    clock = SimpleNamespace(now=100., phase=AirframePhase.MULTICOPTER, count=0)
    async def sleep(duration):
        clock.now += duration
    async def observe():
        clock.count += 1
        stale_spike = case == "stale_pose" and 105. <= clock.now < 105.06
        invalid_interval = 105. <= clock.now < 105.06
        value = packet(clock.now, phase=AirframePhase.UNKNOWN if case == "unknown" and invalid_interval else clock.phase,
            z=-36. if stale_spike else -30., fresh=not stale_spike,
            nav_state=5 if case == "takeover" and invalid_interval else 4)
        value["aircraft_state"]["sequence"] = clock.count
        return value
    def pilot(_socket, _isolation, event, _initial, _contract, **_kwargs):
        clock.phase = event.requested_phase
        return {"returncode": 0}
    monkeypatch.setattr(tool, "native_pilot_transition", Mock(side_effect=pilot))
    rt = runtime(tmp_path)
    rt.output.mkdir()
    rt.fixture["forward"] = ({"request_at_s": 3.51, "capture_s": 3.65} if case == "late_phase"
                             else {"request_at_s": 4., "capture_s": 9.})
    rt.socket, rt.verify = Path("unused-mock-socket"), Mock()
    heights = []
    result = await tool.capture(SimpleNamespace(observe=observe), rt, aircraft_state().binding, "runtime",
        io.StringIO(), "forward", AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING, {}, -30., heights,
        clock=lambda: clock.now, sleep=sleep)
    expected = 6. if case == "stale_pose" else 0.
    assert max(heights) == expected and result["maximum_full_window_observed_excursion_m"] == expected
    if case == "stale_pose": assert result["observation_issues"]["reply_not_fresh"] >= 1
    if case == "unknown": assert result["observation_issues"]["phase_unknown"] >= 1
    if case == "takeover": assert result["observation_issues"]["native_hold_exited"] >= 1
    assert result["settled_healthy"] is False
    assert not result["performance_passed"]
    assert tool.native_pilot_transition.call_count == 1


@pytest.mark.parametrize("healthy", [True, False])
@pytest.mark.asyncio
async def test_reverse_admission_does_not_hide_forward_performance_failure(tmp_path, monkeypatch, healthy):
    rt = runtime(tmp_path)
    rt.clock = Mock(side_effect=[{"source_clock_us": 1}, {"source_clock_us": 2}])
    monkeypatch.setattr(tool, "transition_source_contract", Mock(return_value={}))
    refs, shared_heights = [], []
    async def capture(*arguments):
        stage, reference, heights = arguments[5], arguments[9], arguments[10]
        refs.append(reference)
        shared_heights.append(heights)
        heights.append(3. if stage == "forward" else .5)
        return {"settled_healthy": healthy, "performance_passed": False}
    monkeypatch.setattr(tool, "capture", capture)
    result, _, _ = await tool.capture_cycle(None, rt, None, "runtime", None, packet())
    assert not result["response_passed"] and result["maximum_full_window_observed_excursion_m"] == 3.
    assert len(refs) == (2 if healthy else 1)
    if healthy:
        assert refs == [-30., -30.] and shared_heights[0] is shared_heights[1]
    else:
        assert result["back"]["skipped"]


@pytest.mark.parametrize("field", ["image", "user", "network", "privileged", "devices", "ports", "mount", "token", "running"])
def test_sidecar_cannot_escape_owned_primary_namespace_or_identity(tmp_path, monkeypatch, field):
    rt = runtime(tmp_path)
    rt.socket = tmp_path / "guidance.sock"
    records = {P: info(rt, P), A: info(rt, A)}
    side = records[A]
    if field == "image": side["Image"] = "other"
    elif field == "user": side["Config"]["User"] = "0:0"
    elif field == "network": side["HostConfig"]["NetworkMode"] = "host"
    elif field == "privileged": side["HostConfig"]["Privileged"] = True
    elif field == "devices": side["HostConfig"]["Devices"] = ["/dev/ttyUSB0"]
    elif field == "ports": side["NetworkSettings"]["Ports"] = {"8888": "published"}
    elif field == "mount": side["Mounts"][0]["Destination"] = "/work"
    elif field == "token": side["Config"]["Labels"][tool.shared.LABEL] = "replacement"
    else: side["State"]["Running"] = False
    monkeypatch.setattr(tool.shared, "command", lambda *argv: json.dumps([records[argv[-1]]]))
    verify = Mock(return_value=rt.isolation)
    monkeypatch.setattr(tool, "verify_simulator", verify)
    with pytest.raises((ValueError, RuntimeError)):
        rt.verify()
    assert not verify.called


@pytest.mark.parametrize("flush_failure", [False, True])
def test_cleanup_flushes_and_stops_both_original_cids_without_a_mode(tmp_path, monkeypatch, flush_failure):
    rt = runtime(tmp_path)
    rt.output.mkdir()
    monkeypatch.setattr(tool.shared, "owned_container_info", lambda cid, token: info(rt, cid))
    stops = []
    monkeypatch.setattr(tool.shared, "stop_owned_container", lambda cid, token: stops.append((cid, token)) or {"stopped": True})
    calls = []
    def command(argv, **kwargs):
        calls.append(argv)
        if any("px4-logger" in part for part in argv) and flush_failure:
            raise RuntimeError("flush failed")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    rt.command = command
    errors = rt.cleanup()
    assert [cid for cid, _ in stops] == [A, P]
    assert all(token == rt.token for _, token in stops)
    assert any("px4-logger" in str(argv) and argv[-1] == "stop" for argv in calls)
    assert not any("commander" in str(argv) or "mode" in argv for argv in calls)
    assert bool(errors) == flush_failure


def test_start_installs_logger_before_primary_and_preserves_adapter_ros_workspace(tmp_path, monkeypatch):
    rt = runtime(tmp_path)
    rt.created, rt.primary, rt.sidecar, rt.isolation = [], None, None, None
    alias = tmp_path / "alias"
    def temporary(**kwargs):
        alias.mkdir(mode=0o700)
        return str(alias)
    monkeypatch.setattr(tool, "tempfile", SimpleNamespace(mkdtemp=temporary))
    launches = []
    def launch(argv, name):
        assert tool.digest(rt.output / "simulator/rootfs/fs/etc/logging/logger_topics.txt") == rt.assets["logger_sha256"]
        launches.append(argv)
        return P if len(launches) == 1 else A
    rt.launch = launch
    rt.start()
    assert "PX4_PARAM_MIS_TAKEOFF_ALT=30" in launches[0] and "PX4_PARAM_SDLOG_PROFILE=131" in launches[0]
    assert "container:" + P in launches[1]
    assert any("dst=/runtime" in arg for arg in launches[1])
    assert not any("dst=/work" in arg for arg in launches[1])
    assert "source /work/ws/install/setup.bash" in (rt.output / "simulator/adapter.sh").read_text()
    assert launches[1][-1] == "/runtime/agent.sh"
    agent = (rt.output / "simulator/agent.sh").read_text()
    assert "exec /opt/pixeagle/agent/bin/MicroXRCEAgent" in agent
    assert "pixeagle-native-guidance" not in agent and "wait -n" not in agent
    assert not list((rt.output / "simulator/rootfs").glob("fs/parameters*.bson"))


@pytest.mark.parametrize("problem", ["bootstrap", "owner", "stale", "rescue", "after-arm-rescue", "readback", "close", "none"])
@pytest.mark.asyncio
async def test_execute_has_no_authority_before_verified_native_preflight_and_always_cleans(tmp_path, monkeypatch, problem):
    options = args(tmp_path)
    fixture = tool.scenario(tool.SCENARIOS / "sih-standard-hold-cycle.json")
    actions, cleaned, verified = [], [], []
    class FakeRuntime:
        def __init__(self, *unused):
            self.output, self.token, self.created = options.output, "connection-1", [P, A]
            self.socket = SimpleNamespace(is_socket=lambda: True)
            self.isolation = {"aircraft_uid": "aircraft-a"}
        def start(self): self.output.mkdir()
        async def bootstrap(self, deadline):
            if problem == "bootstrap": raise TimeoutError("DDS session not ready before deadline")
        def verify(self): verified.append(True)
        def logger(self, stage): pass
        def cli(self, alias, *arguments, **kwargs):
            actions.append((alias, arguments))
            if alias == "param":
                altitude = 20 if problem == "readback" else 30
                return SimpleNamespace(stdout=f"MIS_TAKEOFF_ALT: {altitude}\nSDLOG_PROFILE: 131\nSYS_AUTOSTART: 10043\n")
            armed = any(op == "commander" and value == ("arm",) for op, value in actions)
            return SimpleNamespace(stdout="timestamp: 1000000 (0.01 seconds ago)\npre_flight_checks_pass: true\n"
                + f"arming_state: {2 if armed else 1}\n")
        def cleanup(self): cleaned.extend(self.created); return []
    class Client:
        async def connect(self):
            return NativeCapabilities("runtime", "synthetic", 2, True, True, False, True, 23)
        async def bind(self, binding): self.binding = binding
        async def observe(self):
            self.observed = getattr(self, "observed", 0) + 1
            armed = any(op == "commander" and value == ("arm",) for op, value in actions)
            changes = ({"owner_confirmed": True} if problem == "owner" else
                       {"fresh": False} if problem == "stale" and self.observed == 1 else
                       {"rescue_active": True} if problem == "rescue" or (problem == "after-arm-rescue" and armed) else {})
            return packet(tool.time.monotonic(), **changes)
        async def close(self):
            if problem == "close": raise RuntimeError("close failure retained")
    monkeypatch.setattr(tool, "Runtime", FakeRuntime)
    monkeypatch.setattr(tool, "NativeGuidanceClient", lambda _: Client())
    monkeypatch.setattr(tool, "verify_adapter", Mock())
    monkeypatch.setattr(tool, "verify_adapter_image", Mock())
    monkeypatch.setattr(tool.shared, "verified_simulation_build", Mock(return_value=("sih", {}, {})))
    monkeypatch.setattr(tool, "bootstrap_contract", Mock(return_value={"autostart": 10043}))
    monkeypatch.setattr(tool, "wait_stable", AsyncMock(return_value=packet()))
    monkeypatch.setattr(tool, "capture_cycle", AsyncMock(return_value=({"response_passed": True}, {}, {})))
    monkeypatch.setattr(tool, "audit_ulog", Mock(return_value={"passed": True}))
    result = await tool.execute(options, fixture)
    assert cleaned == [P, A]
    flight = [args for alias, args in actions if alias == "commander"]
    if problem in {"bootstrap", "owner", "rescue", "readback"}:
        assert flight == [] and not result["passed"]
    elif problem == "after-arm-rescue":
        assert flight == [("arm",)] and not result["passed"]
    else:
        assert flight == [("arm",), ("takeoff",)] and len(verified) >= 3
        assert result["passed"] is (problem in {"none", "stale"})
    if problem == "close": assert "close failure retained" in str(result["errors"])


@pytest.mark.asyncio
async def test_bad_build_manifest_refuses_before_runtime_staging(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, "verify_adapter", Mock())
    monkeypatch.setattr(tool.shared, "verified_simulation_build", Mock(side_effect=ValueError("invalid manifest")))
    constructor = Mock(side_effect=AssertionError("staged before verification"))
    monkeypatch.setattr(tool, "Runtime", constructor)
    with pytest.raises(ValueError, match="invalid manifest"):
        await tool.execute(args(tmp_path), tool.scenario(tool.SCENARIOS / "sih-standard-hold-cycle.json"))
    assert not constructor.called and not (tmp_path / "run").exists()


@pytest.mark.parametrize("unready", ["observation", "vehicle_status"])
@pytest.mark.asyncio
async def test_prearm_unready_state_or_stale_native_status_exhausts_same_deadline(tmp_path, monkeypatch, unready):
    rt = runtime(tmp_path)
    rt.verify = Mock()
    rt.cli = Mock(return_value=SimpleNamespace(stdout="timestamp: 1000000 (10 seconds ago)\n"
        "pre_flight_checks_pass: true\narming_state: 1\n"))
    current = [100.]
    async def sleep(duration): current[0] += duration
    async def observation(): return packet(current[0], fresh=unready != "observation")
    if unready == "observation":
        rt.cli.return_value.stdout = "timestamp: 1000000 (0.01 seconds ago)\npre_flight_checks_pass: true\narming_state: 1\n"
    client = SimpleNamespace(observe=observation)
    with pytest.raises(TimeoutError, match="Existing 30s"):
        await tool.admit_flight_action(client, rt, aircraft_state().binding, "runtime", io.StringIO(),
            "arm", 101., clock=lambda: current[0], sleep=sleep)
    assert rt.verify.call_count == 2
    assert all(call.args[0] == "listener" for call in rt.cli.call_args_list)


def test_adapter_file_and_compiled_source_pins_refuse_changes_without_processes(tmp_path, monkeypatch):
    repository, bundle = tmp_path / "repo", tmp_path / "bundle"
    repository.mkdir()
    (repository / "source.cpp").write_text("compiled source")
    adapter = bundle / "adapter/pixeagle-native-guidance"
    adapter.parent.mkdir(parents=True)
    adapter.write_bytes(b"SYNTHETIC executable fixture")
    files = {"adapter/pixeagle-native-guidance": {"sha256": tool.digest(adapter)}}
    index = tmp_path / "files.json"
    index.write_text(json.dumps(files))
    assets = dict(file_manifest_sha256=tool.digest(index), bundle_files=1,
        adapter_sha256=tool.digest(adapter), compiled_inputs={"source.cpp": tool.digest(repository / "source.cpp")})
    monkeypatch.setattr(tool, "ROOT", repository)
    tool.verify_adapter(bundle, index, assets)
    (repository / "source.cpp").write_text("changed")
    with pytest.raises(ValueError, match="source changed"):
        tool.verify_adapter(bundle, index, assets)


@pytest.mark.parametrize("kind", ["clean", "estimator_spike", "truth_spike", "dropout", "corrupt", "partial", "epoch"])
def test_closed_log_full_window_truth_cannot_filter_excursions_or_unknowns(tmp_path, kind):
    (tmp_path / "closed.ulg").write_bytes(b"SYNTHETIC parser fixture; not a real ULog")
    stamps = [1_000_000, 1_200_000, 1_500_000, 1_800_000, 2_000_000]
    data = {name: {"timestamp": stamps, "z": [-30.] * 5, "z_valid": [True, True, False, True, True]}
            for name in ["vehicle_local_position", "vehicle_local_position_groundtruth"]}
    if kind == "estimator_spike": data["vehicle_local_position"]["z"][2] = -33.
    if kind == "truth_spike": data["vehicle_local_position_groundtruth"]["z"][2] = -33.
    if kind == "partial":
        for value in data.values(): value["timestamp"], value["z"] = [1_800_000, 2_000_000], [-30., -30.]
    log = SimpleNamespace(dropouts=[1] if kind == "dropout" else [], file_corruption=kind == "corrupt",
                          get_dataset=lambda name: SimpleNamespace(data=data[name]))
    start = {"source_clock_us": 1_000_000, "incarnation": "same"}
    end = {"source_clock_us": 2_000_000, "incarnation": "other" if kind == "epoch" else "same"}
    if kind in {"partial", "epoch"}:
        with pytest.raises(ValueError): tool.audit_ulog(tmp_path, start, end, parser=lambda _: log)
    else:
        result = tool.audit_ulog(tmp_path, start, end, parser=lambda _: log)
        assert result["passed"] is (kind == "clean")
        if "spike" in kind:
            assert max(topic["maximum_excursion_m"] for topic in result["topics"].values()) == 3.
            assert not any(topic["filtered_by_pose_flags"] for topic in result["topics"].values())


DDS_STATUS = """INFO  [uxrce_dds_client] Running, connected
INFO  [uxrce_dds_client] Using transport:     udp
INFO  [uxrce_dds_client] Agent IP:            127.0.0.1
INFO  [uxrce_dds_client] Agent port:          8888
INFO  [uxrce_dds_client] timesync converged: true
"""


@pytest.mark.parametrize("change", ["ready", "disconnected", "timesync", "transport", "ip", "port", "duplicate", "exit"])
def test_dds_gate_matches_exact_source_status_not_exit_or_connected_substring(change):
    text = DDS_STATUS
    if change == "disconnected": text = text.replace("Running, connected", "Running, disconnected")
    if change == "timesync": text = text.replace("converged: true", "converged: false")
    if change == "transport": text = text.replace("udp", "serial")
    if change == "ip": text = text.replace("127.0.0.1", "10.0.0.2")
    if change == "port": text = text.replace("8888", "9999")
    if change == "duplicate": text += DDS_STATUS
    assert tool.dds_session_ready(SimpleNamespace(returncode=1 if change == "exit" else 0, stdout=text)) is (change == "ready")


def test_only_fixed_owned_private_primary_status_can_bypass_socket_readiness(tmp_path, monkeypatch):
    rt = runtime(tmp_path)
    rt.isolation = None
    monkeypatch.setattr(tool.shared, "owned_container_info", lambda cid, token: info(rt, cid))
    rt.command = Mock(return_value=SimpleNamespace(returncode=0, stdout=DDS_STATUS, stderr=""))
    assert tool.dds_session_ready(rt.bootstrap_status(timeout=2.))
    command = rt.command.call_args.args[0]
    assert command == ["docker", "exec", "--user", f"{os.getuid()}:{os.getgid()}", P,
                       "/opt/px4/bin/px4-uxrce_dds_client", "--instance", "0", "status"]
    with pytest.raises(ValueError): rt.cli("commander", "arm")
    with pytest.raises(ValueError): rt.cli("uxrce_dds_client", "status")


@pytest.mark.parametrize("changed", ["mount", "workdir"])
def test_bootstrap_status_refuses_nonprivate_primary_before_fixed_probe(tmp_path, monkeypatch, changed):
    rt = runtime(tmp_path)
    primary = info(rt, P)
    if changed == "mount": primary["Mounts"][0]["Source"] = "/unrelated"
    else: primary["Config"]["WorkingDir"] = "/work"
    monkeypatch.setattr(tool.shared, "owned_container_info", lambda cid, token: primary if cid == P else info(rt, cid))
    rt.command = Mock(side_effect=AssertionError("probe before private isolation"))
    with pytest.raises(ValueError, match="private primary workdir"):
        rt.bootstrap_status(timeout=2.)
    assert not rt.command.called


@pytest.mark.parametrize("failure", [None, "never-ready", "socket-timeout", "sidecar-death", "primary-death", "exec-failure", "late-inspection"])
@pytest.mark.asyncio
async def test_bootstrap_orders_session_then_one_adapter_and_shares_original_deadline(tmp_path, failure):
    rt = runtime(tmp_path)
    rt.output.mkdir()
    now, events, probes = [0.], [], [0]
    async def sleep(duration): now[0] += duration
    def primary():
        events.append("primary")
        if failure == "primary-death": raise ValueError("primary dead")
        if failure == "late-inspection" and probes[0] >= 3: now[0] = 45.
    def sidecar():
        events.append("sidecar")
        if failure == "sidecar-death": raise ValueError("sidecar dead")
    def status(**kwargs):
        probes[0] += 1
        now[0] += 4.
        events.append("status")
        ready = probes[0] >= 3 and failure != "never-ready"
        return SimpleNamespace(returncode=0, stdout=DDS_STATUS if ready else DDS_STATUS.replace("connected", "disconnected"), stderr="")
    def launch(argv, **kwargs):
        events.append("adapter")
        assert probes[0] >= 3 and rt.adapter_requested
        assert argv[:3] == ["docker", "exec", "-d"] and argv[-3:] == [A, "bash", "/runtime/adapter.sh"]
        assert kwargs["timeout"] <= 45. - now[0]
        if failure == "exec-failure": raise RuntimeError("exec failed after possible fork")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    rt.primary_info, rt.sidecar_info, rt.bootstrap_status, rt.command = primary, sidecar, status, launch
    rt.socket = SimpleNamespace(is_socket=lambda: failure != "socket-timeout")
    if failure is None:
        await rt.bootstrap(45., clock=lambda: now[0], sleep=sleep)
        assert events.count("adapter") == 1 and now[0] < 45.
    else:
        with pytest.raises((ValueError, RuntimeError, TimeoutError)):
            await rt.bootstrap(45., clock=lambda: now[0], sleep=sleep)
        assert events.count("adapter") <= 1
    if failure in {"never-ready", "late-inspection", "sidecar-death", "primary-death"}:
        assert "adapter" not in events
    if rt.adapter_requested:
        with pytest.raises(ValueError, match="one-shot"):
            await rt.bootstrap(45., clock=lambda: now[0], sleep=sleep)


def no_pitot_fixture():
    return tool.scenario(tool.SCENARIOS / "gazebo-quadtailsitter-no-pitot-hold-cycle.json")


def test_no_pitot_fixture_changes_only_declared_installation_and_resource():
    stock = tool.scenario(tool.SCENARIOS / "gazebo-quadtailsitter-hold-cycle.json")
    assert no_pitot_fixture() == stock | {"resource_variant": "quadtailsitter-no-pitot-v1",
        "parameters": {"MIS_TAKEOFF_ALT": 30, "SYS_HAS_NUM_ASPD": 0}}
    assert "differential_pressure 0 0" in (tool.SCENARIOS / "logger_topics.txt").read_text().splitlines()
    assert tool.digest(tool.SCENARIOS / "logger_topics.txt") == json.loads(tool.ASSETS.read_text())["logger_sha256"]


@pytest.mark.parametrize("change", [
    {"resource_variant": None}, {"resource_variant": []}, {"resource_variant": "unknown"},
    {"model": "sihsim_xvert"}, {"parameters": {"MIS_TAKEOFF_ALT": 30}},
    {"parameters": {"MIS_TAKEOFF_ALT": 30, "SYS_HAS_NUM_ASPD": 1}},
    {"parameters": {"MIS_TAKEOFF_ALT": 30, "SYS_HAS_NUM_ASPD": False}},
    {"parameters": {"MIS_TAKEOFF_ALT": 30, "SYS_HAS_NUM_ASPD": 0., "FW_USE_AIRSPD": 0}},
])
def test_no_pitot_fixture_rejects_ambiguous_or_disabled_control_configuration(tmp_path, change):
    value = {"schema_version": 1, "model": "gz_quadtailsitter", "resource_variant": "quadtailsitter-no-pitot-v1",
        "parameters": {"MIS_TAKEOFF_ALT": 30, "SYS_HAS_NUM_ASPD": 0},
        "forward": {"request_at_s": 8, "capture_s": 48}, "back": {"request_at_s": 8, "capture_s": 48}} | change
    path = tmp_path / "case.json";path.write_text(json.dumps(value))
    with pytest.raises(ValueError): tool.scenario(path)
    value.pop("resource_variant", None);path.write_text(json.dumps(value))
    if "SYS_HAS_NUM_ASPD" in value["parameters"]:
        with pytest.raises(ValueError): tool.scenario(path)


@pytest.mark.parametrize("declared,variant,accepted", [
    (False, None, True), (True, {"name": "quadtailsitter-no-pitot-v1"}, True),
    (False, {"name": "quadtailsitter-no-pitot-v1"}, False), (True, None, False),
    (True, {"name": "other"}, False), (True, "quadtailsitter-no-pitot-v1", False),
])
def test_no_pitot_manifest_pairing_precedes_runtime_staging(tmp_path, monkeypatch, declared, variant, accepted):
    fixture = tool.scenario(tool.SCENARIOS / "gazebo-quadtailsitter-hold-cycle.json")
    if declared: fixture.update(resource_variant="quadtailsitter-no-pitot-v1", parameters={"MIS_TAKEOFF_ALT": 30, "SYS_HAS_NUM_ASPD": 0})
    manifest = {"build": {"model": "quadtailsitter"}}
    if variant is not None: manifest["build"]["resource_variant"] = variant
    monkeypatch.setattr(tool, "verify_adapter", Mock())
    monkeypatch.setattr(tool.shared, "verified_simulation_build", Mock(return_value=("gazebo", {}, manifest)))
    image = Mock();monkeypatch.setattr(tool, "verify_adapter_image", image)
    monkeypatch.setattr(tool, "bootstrap_contract", Mock(return_value={}))
    constructor = Mock();monkeypatch.setattr(tool, "Runtime", constructor)
    if accepted:
        tool.verified_runtime(args(tmp_path), fixture)
        constructor.assert_called_once()
    else:
        with pytest.raises(ValueError, match="variant"): tool.verified_runtime(args(tmp_path), fixture)
        constructor.assert_not_called();image.assert_not_called()
    assert not args(tmp_path).output.exists()


@pytest.mark.parametrize("stdout,stderr,code,accepted", [
    ("never published\n", "", 0, True), ("TOPIC: differential_pressure\n", "", 0, False),
    ("never published\nTOPIC: differential_pressure\n", "", 0, False),
    ("never published\n", "", 1, False), ("", "", 0, False),
    ("never published\n", "unknown topic", 0, False),
])
def test_no_pitot_probe_requires_exact_all_instance_absence(tmp_path, stdout, stderr, code, accepted):
    rt = runtime(tmp_path);rt.output.mkdir()
    rt.cli = Mock(return_value=SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code))
    if accepted: rt.verify_sensor_absence("before-arm")
    else:
        with pytest.raises(ValueError, match="publisher"): rt.verify_sensor_absence("before-arm")
    rt.cli.assert_called_once_with("listener", "differential_pressure", "-n", "1", check=False)
    retained = json.loads((rt.output / "before-arm-differential-pressure.json").read_text())
    assert retained["stdout"] == stdout and retained["returncode"] == code


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["publisher", "cancel"])
@pytest.mark.parametrize("after_arm", [False, True])
async def test_no_pitot_probe_failure_closes_both_original_containers_before_arm(tmp_path, monkeypatch, failure, after_arm):
    import asyncio
    fixture = {"parameters": {"MIS_TAKEOFF_ALT": 30, "SYS_HAS_NUM_ASPD": 0},
               "resource_variant": "quadtailsitter-no-pitot-v1"}
    rt = runtime(tmp_path);rt.fixture = fixture;rt.start = lambda: rt.output.mkdir()
    rt.socket = tmp_path / "observer.sock"
    rt.bootstrap = AsyncMock();rt.verify = Mock();rt.logger = Mock()
    rt.cli = Mock(return_value=SimpleNamespace(stdout="MIS_TAKEOFF_ALT: 30\nSYS_HAS_NUM_ASPD: 0\n"
        "FW_USE_AIRSPD: 1\nSYS_AUTOSTART: 4018\nSDLOG_PROFILE: 131\n"))
    error = ValueError("publisher present") if failure == "publisher" else asyncio.CancelledError()
    rt.verify_sensor_absence = Mock(side_effect=[None, error] if after_arm else error)
    rt.cleanup = Mock(return_value=[])
    client = SimpleNamespace(connect=AsyncMock(return_value=NativeCapabilities("runtime", "synthetic", 2, True, True, False, True, 23)),
        bind=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(tool, "verified_runtime", lambda *_: (rt, {"autostart": 4018, "native_default_readback": {"FW_USE_AIRSPD": 1}}, "gazebo"))
    monkeypatch.setattr(tool, "NativeGuidanceClient", lambda *_: client)
    admission = AsyncMock();monkeypatch.setattr(tool, "admit_flight_action", admission)
    from tools import run_native_guidance_cycle as cycle
    monkeypatch.setattr(cycle, "NativeGuidanceClient", lambda *_: client)
    options = args(tmp_path);options.mount = "HORIZONTAL"
    case = cycle.case(tool.SCENARIOS / "gazebo-guidance-no-pitot.json")
    result = await cycle.execute(options, case)
    assert result["errors"] and not result["passed"]
    assert rt.cli.call_args_list == [(("param", "show"),)] + ([(("commander", "arm"),)] if after_arm else [])
    assert admission.await_count == (1 if after_arm else 0)
    rt.cleanup.assert_called_once();client.close.assert_awaited_once()
    assert rt.created == [P, A]


@pytest.mark.asyncio
async def test_no_pitot_standalone_transition_execute_refuses_before_staging(tmp_path, monkeypatch, capsys):
    verify = Mock(side_effect=AssertionError("unsupported native transition runtime"))
    monkeypatch.setattr(tool, "verified_runtime", verify)
    fixture = no_pitot_fixture()
    with pytest.raises(ValueError, match="guidance only"):
        await tool.execute(args(tmp_path), fixture)
    assert tool.main(["--scenario", str(tool.SCENARIOS / "gazebo-quadtailsitter-no-pitot-hold-cycle.json")]) == 0
    assert json.loads(capsys.readouterr().out)["runner_supported"] is False
    verify.assert_not_called();assert not args(tmp_path).output.exists()


@pytest.mark.parametrize("bad_source", [None, "bounds", "default", "probe", "reference"])
def test_no_pitot_boot_uses_native_bounds_default_and_pinned_absence_semantics(tmp_path, bad_source):
    import yaml
    source = tmp_path / "source"
    files = {"ROMFS/px4fmu_common/init.d-posix/rcS":
        '"PX4_PARAM_"*) param set\n. px4-rc.simulator\ncommander start\nnavigator start\n',
        "src/modules/navigator/mission_params.yaml": yaml.safe_dump({"parameters": [{"definitions": {
            "MIS_TAKEOFF_ALT": {"min": 0}}}]}),
        "src/modules/vtol_att_control/vtol_att_control_params.yaml": yaml.safe_dump({"parameters": [{"definitions": {}}]}),
        tool.DDS_STATUS_SOURCE: "source", tool.SYSTEM_PARAMETERS: yaml.safe_dump({"parameters": [{"definitions": {
            "SYS_HAS_NUM_ASPD": {"min": 1 if bad_source == "bounds" else 0, "max": 1}}}]}),
        tool.FW_PARAMETERS: yaml.safe_dump({"parameters": [{"definitions": {
            "FW_USE_AIRSPD": {"default": 0 if bad_source == "default" else 1}}}]}),
        "src/systemcmds/topic_listener/listener_main.cpp": "pinned probe semantics"}
    for name, text in files.items():
        path = source / name;path.parent.mkdir(parents=True, exist_ok=True);path.write_text(text)
    airframe = source / "ROMFS/px4fmu_common/init.d-posix/airframes/4018_gz_quadtailsitter"
    airframe.parent.mkdir();airframe.write_text("param set-default FW_AIRSPD_MIN " + ("13" if bad_source == "reference" else "14") + "\n")
    supplemental = {tool.SYSTEM_PARAMETERS, tool.FW_PARAMETERS, "src/systemcmds/topic_listener/listener_main.cpp"}
    assets = {"bootstrap_files": {name: tool.digest(source/name) for name in files if name not in supplemental},
        "no_pitot_sources": {name: tool.digest(source/name) for name in supplemental}}
    if bad_source == "probe": (source/"src/systemcmds/topic_listener/listener_main.cpp").write_text("changed")
    if bad_source:
        with pytest.raises(ValueError): tool.bootstrap_contract(source, no_pitot_fixture(), assets)
    else:
        boot = tool.bootstrap_contract(source, no_pitot_fixture(), assets)
        assert boot["native_default_readback"] == {"FW_USE_AIRSPD": 1}
        assert boot["no_pitot_source_sha256"] == assets["no_pitot_sources"]
        assert "FW_USE_AIRSPD" not in no_pitot_fixture()["parameters"]
        with pytest.raises(ValueError, match="readback"):
            tool.readback("FW_USE_AIRSPD: 0\n", boot["native_default_readback"])
