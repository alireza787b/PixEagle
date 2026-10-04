"""Authenticated loopback HTTP impairment scenarios; no camera/PX4 transport.

Delay and drops are injected into the sender schedule, not the host network.
This establishes a software envelope, not radio bandwidth or motor behavior.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from tools.native_integration_fixture import create_app

PATH = "/api/v1/actions/gimbal-control"


def wait_until(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    assert predicate()


@dataclass
class LinkBench:
    runtime: object
    client: object
    headers: dict
    writes: list
    owner: object

    def request(self, operation, sequence, *, gesture="link-test", value=0.5, guard=None):
        body = dict(operation=operation, gesture_id=gesture, sequence=sequence,
                    confirm=True, idempotency_key=f"{gesture}-{operation}-{sequence}",
                    camera_context=dict(client_id="link-client", guard=guard or self.runtime.guard()))
        if operation != "stop":
            body["intent"] = dict(axis="pan", value=value)
        started = time.monotonic()
        response = self.client.post(PATH, json=body, headers=self.headers)
        return response, started, time.monotonic()

    def begin(self):
        response, _, _ = self.request("manual_begin", 0)
        assert response.status_code == 202, response.text
        return self.runtime.guard()

    def renew(self, sequence, **kwargs):
        return self.request("manual_update", sequence, **kwargs)

    def emit(self, scenario, **fields):
        print("CAMERA_LINK " + json.dumps(dict(scenario=scenario, **fields), sort_keys=True))


@pytest.fixture
def bench(tmp_path, monkeypatch):
    from classes.parameters import Parameters

    monkeypatch.setattr(Parameters, "USE_MAVLINK2REST", Parameters.USE_MAVLINK2REST)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    app = create_app(port=port, no_aircraft=True, mock_camera=True,
                     audit_path=tmp_path / "audit.jsonl")
    owner = app.state.fixture_owner.app_controller
    runtime = owner.camera_runtime
    writes = []
    control = runtime.provider.manual_control
    original_send, original_stop = control.send_manual_intent, control.stop

    def send(axis, value):
        writes.append((time.monotonic(), dict(axis=axis, value=value)))
        original_send(axis, value)

    def stop():
        writes.append((time.monotonic(), dict(stop=True)))
        return original_stop()

    control.send_manual_intent, control.stop = send, stop
    config = uvicorn.Config(app, log_level="error", access_log=False,
                            timeout_graceful_shutdown=1)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    try:
        wait_until(lambda: server.started)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3, trust_env=False) as client:
            login = client.post("/api/v1/auth/login", json=dict(username="operator", password="fixture-only"))
            assert login.status_code == 200, login.text
            yield LinkBench(runtime, client, {"x-pixeagle-csrf": login.json()["csrf_token"]}, writes, owner)
    finally:
        server.should_exit = True
        thread.join(timeout=3)
        listener.close()
        assert not thread.is_alive()


@pytest.mark.parametrize("drop_sequences", [(), (5, 9)])
def test_delayed_renewals_with_isolated_drops(bench, drop_sequences):
    """20-60 ms sender delay; isolated misses keep admission gaps <350 ms."""
    guard = bench.begin()
    base = time.monotonic()
    accepted = []

    def packet(sequence):
        delay = (20, 60, 40)[sequence % 3] / 1000
        time.sleep(max(0, base + (sequence - 1) * 0.1 + delay - time.monotonic()))
        response, started, finished = bench.renew(sequence, guard=guard)
        assert response.status_code == 202, response.text
        accepted.append(response.json()["result"]["manual"]["accepted_at_monotonic"])
        return (finished - started) * 1000

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(packet, sequence) for sequence in range(1, 15)
                   if sequence not in drop_sequences]
        roundtrips = [future.result() for future in futures]
    assert bench.runtime.manual_snapshot()["state"] == "moving"
    assert not any("stop" in fields for _, fields in bench.writes)
    result, _, _ = bench.request("stop", 15, guard=guard)
    assert result.status_code == 202, result.text
    timing = result.json()["result"]["timing"]
    dispatch = next(timestamp for timestamp, fields in bench.writes if "stop" in fields)
    stop_ms = (dispatch - timing["received_at_monotonic"]) * 1000
    assert 0 <= stop_ms <= 100
    gaps = [(b - a) * 1000 for a, b in zip(sorted(accepted), sorted(accepted)[1:])]
    bench.emit("isolated_drop" if drop_sequences else "delayed_renewals",
               nominal_renewal_ms=100, sender_delay_ms=[20, 60, 40],
               dropped_sequences=list(drop_sequences), accepted=len(accepted),
               max_admission_gap_ms=max(gaps), max_http_round_trip_ms=max(roundtrips),
               stop_dispatch_from_backend_receipt_ms=stop_ms)


def test_disconnected_client_expires_and_late_packets_cannot_revive(bench):
    guard = bench.begin()
    response, _, _ = bench.renew(1, guard=guard)
    assert response.status_code == 202, response.text
    accepted = response.json()["result"]["manual"]["accepted_at_monotonic"]
    wait_until(lambda: any("value" in fields for _, fields in bench.writes))
    wait_until(lambda: bench.runtime.manual_snapshot()["state"] == "expired")
    first_stop = next(timestamp for timestamp, fields in bench.writes if "stop" in fields)
    expiry_ms = (first_stop - accepted) * 1000
    assert 350 <= expiry_ms <= 400
    late, _, _ = bench.renew(2, guard=guard, value=-1)
    assert late.status_code == 409, late.text
    assert not any("value" in fields for timestamp, fields in bench.writes if timestamp > first_stop)
    bench.emit("disconnect_and_burst_loss", lease_ms=350,
               expiry_stop_from_last_renewal_ms=expiry_ms,
               delayed_update_status=late.status_code, obsolete_motion_after_stop=0)


def test_reordered_updates_and_delayed_packet_after_release(bench):
    guard = bench.begin()
    high, _, _ = bench.renew(2, guard=guard, value=-0.5)
    assert high.status_code == 202, high.text
    wait_until(lambda: any(fields.get("value") == -0.5 for _, fields in bench.writes))
    stale, _, _ = bench.renew(1, guard=guard, value=1)
    assert stale.status_code == 409, stale.text
    stop, _, _ = bench.request("stop", 4, guard=guard)
    assert stop.status_code == 202, stop.text
    stop_at = next(timestamp for timestamp, fields in bench.writes if "stop" in fields)
    late, _, _ = bench.renew(3, guard=guard, value=1)
    assert late.status_code == 409, late.text
    assert not any(fields.get("value") == 1 for _, fields in bench.writes)
    assert not any("value" in fields for timestamp, fields in bench.writes if timestamp > stop_at)
    bench.emit("reorder_and_release", arrival_sequence=[2, 1, 4, 3],
               statuses=[high.status_code, stale.status_code, stop.status_code, late.status_code],
               obsolete_motion_after_stop=0)


def test_release_while_camera_takeover_waits(bench):
    gate = threading.Event()

    async def wait_for_takeover(command_guard):
        while not gate.is_set():
            await asyncio.sleep(0.005)
        with command_guard():
            pass

    bench.runtime.provider.manual_control.prepare_manual = wait_for_takeover
    guard = bench.begin()
    renewed, _, _ = bench.renew(1, guard=guard)
    assert renewed.status_code == 202, renewed.text
    released, _, _ = bench.request("stop", 2, guard=guard)
    assert released.status_code == 202, released.text
    gate.set()
    assert not any("value" in fields for _, fields in bench.writes)
    late, _, _ = bench.renew(3, guard=guard)
    assert late.status_code == 409, late.text
    bench.emit("delayed_takeover_release", obsolete_motion=0,
               state=bench.runtime.manual_snapshot()["state"])


@pytest.mark.parametrize("blocked_stage", ["capture", "inference"])
def test_stop_over_http_while_owner_loop_is_blocked(bench, blocked_stage):
    loop = asyncio.new_event_loop()
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        release.wait(3)

    def owner_thread():
        asyncio.set_event_loop(loop)
        try:
            if blocked_stage == "capture":
                block()
            else:
                loop.call_soon(block)
            loop.run_forever()
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    async def schedule(operation):
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(operation(), loop))

    bench.owner._run_on_flight_event_loop = schedule
    thread = threading.Thread(target=owner_thread, daemon=True)
    thread.start()
    try:
        assert entered.wait(1)
        guard = bench.begin()
        renewed, _, _ = bench.renew(1, guard=guard)
        assert renewed.status_code == 202, renewed.text
        wait_until(lambda: any("value" in fields for _, fields in bench.writes))
        stopped, started, finished = bench.request("stop", 2, guard=guard)
        assert stopped.status_code == 202, stopped.text
        received = stopped.json()["result"]["timing"]["received_at_monotonic"]
        dispatch = next(timestamp for timestamp, fields in bench.writes if "stop" in fields)
        dispatch_ms = (dispatch - received) * 1000
        assert 0 <= dispatch_ms <= 100
        assert not release.is_set()
        bench.emit(f"blocked_{blocked_stage}_http_stop",
                   stop_dispatch_from_backend_receipt_ms=dispatch_ms,
                   http_round_trip_ms=(finished - started) * 1000,
                   blocked_owner_released=False)
    finally:
        release.set()
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_second_client_cannot_replace_active_movement(bench):
    guard = bench.begin()
    accepted, _, _ = bench.renew(1, guard=guard)
    assert accepted.status_code == 202, accepted.text
    wait_until(lambda: any("value" in fields for _, fields in bench.writes))
    body = dict(operation="manual_begin", gesture_id="another-client", sequence=0,
                confirm=True, idempotency_key="another-client-begin",
                camera_context=dict(client_id="second-client", guard=guard),
                intent=dict(axis="pan", value=-1))
    foreign = bench.client.post(PATH, json=body, headers=bench.headers)
    assert foreign.status_code == 409, foreign.text
    assert bench.runtime.manual_snapshot()["gesture_id"] == "link-test"
    assert not any(fields.get("value") == -1 for _, fields in bench.writes)
    stopped, _, _ = bench.request("stop", 2, guard=guard)
    assert stopped.status_code == 202, stopped.text
    bench.emit("two_client_arbitration", second_client_status=foreign.status_code,
               replacement_motion=0)


@pytest.mark.parametrize("blocked_stage", ["capture", "inference"])
def test_flight_thread_publishes_while_video_owner_is_blocked(bench, blocked_stage):
    from types import SimpleNamespace
    from classes.flow_controller import FlowController
    from classes.offboard_commander import OffboardCommander
    from tests.unit.drone_interface.test_offboard_commander import _handler

    published = []

    async def send():
        published.append(time.monotonic())
        return True

    flow = object.__new__(FlowController)
    flow.flight_loop, flow.flight_thread = flow.start_flight_event_loop()
    commander = OffboardCommander(SimpleNamespace(send_commands_unified=send), _handler(),
                                 command_rate_hz=20, command_ttl_s=1)
    video_loop = asyncio.new_event_loop()
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        release.wait(3)

    def video_thread():
        asyncio.set_event_loop(video_loop)
        try:
            if blocked_stage == "capture":
                block()
            else:
                video_loop.call_soon(block)
            video_loop.run_forever()
        finally:
            video_loop.close()
            asyncio.set_event_loop(None)

    video = threading.Thread(target=video_thread, daemon=True)
    video.start()
    try:
        assert entered.wait(1)
        assert asyncio.run_coroutine_threadsafe(commander.start(), flow.flight_loop).result(timeout=1)
        wait_until(lambda: len(published) >= 12, timeout=2)
        assert not release.is_set()
        gaps = [(second - first) * 1000 for first, second in zip(published, published[1:])]
        assert max(gaps) < 200
        bench.emit(f"blocked_{blocked_stage}_independent_heartbeat", command_rate_hz=20,
                   publication_count=len(published), max_publication_gap_ms=max(gaps),
                   transport="fake PX4 send; production FlowController flight thread and commander")
    finally:
        asyncio.run_coroutine_threadsafe(commander.stop(publish_final=False), flow.flight_loop).result(timeout=2)
        flow.stop_flight_event_loop()
        release.set()
        video_loop.call_soon_threadsafe(video_loop.stop)
        video.join(timeout=2)
        assert not video.is_alive()
