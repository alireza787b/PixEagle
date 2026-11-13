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
        Config={"User": f"{os.getuid()}:{os.getgid()}", "Labels": {tool.shared.LABEL: runtime.token}},
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
    {"forward": {"request_at_s": 8, "capture_s": 8}},
])
def test_fixture_cannot_select_hardware_hide_tuning_or_change_fixed_gate(tmp_path, change):
    value = tool.scenario(tool.SCENARIOS / "sih-standard-hold-cycle.json") | change
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        tool.scenario(path)
    assert tool.GATE_M == 2.


def test_boot_overlay_source_order_native_bounds_and_actual_readback(tmp_path):
    import yaml
    source = tmp_path / "source"
    texts = {"ROMFS/px4fmu_common/init.d-posix/rcS":
        '"PX4_PARAM_"*) param set\n. px4-rc.simulator\ncommander start\nnavigator start\n',
        "src/modules/navigator/mission_params.yaml": yaml.safe_dump({"parameters": [{"definitions": {
            "MIS_TAKEOFF_ALT": {"min": 0}}}]}),
        "src/modules/vtol_att_control/vtol_att_control_params.yaml": yaml.safe_dump({"parameters": [{"definitions": {
            "VT_F_TRANS_DUR": {"min": .1, "max": 20}}}]})}
    for name, text in texts.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (source / "ROMFS/px4fmu_common/init.d-posix/airframes").mkdir()
    (source / "ROMFS/px4fmu_common/init.d-posix/airframes/10043_sihsim_standard_vtol").write_text("fixture")
    assets = {"bootstrap_files": {name: tool.digest(source / name) for name in texts}}
    fixture = tool.scenario(tool.SCENARIOS / "sih-standard-hold-cycle.json")
    assert tool.bootstrap_contract(source, fixture, assets)["autostart"] == 10043
    tool.readback("MIS_TAKEOFF_ALT: 30\n", fixture["parameters"])
    with pytest.raises(ValueError, match="readback"):
        tool.readback("MIS_TAKEOFF_ALT: 20\n", fixture["parameters"])
    with pytest.raises(ValueError, match="bounds"):
        tool.bootstrap_contract(source, fixture | {"parameters": {"MIS_TAKEOFF_ALT": 30, "VT_F_TRANS_DUR": 21}}, assets)
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
    assert not list((rt.output / "simulator/rootfs").glob("fs/parameters*.bson"))


@pytest.mark.parametrize("problem", ["owner", "stale", "rescue", "after-arm-rescue", "readback", "close", "none"])
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
    if problem in {"owner", "rescue", "readback"}:
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
