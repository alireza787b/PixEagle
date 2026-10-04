"""Production HTTP and JPEG WebSocket routes through the owned relay."""

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from websockets.sync.client import connect

from tools.native_integration_fixture import create_app
from tools.shared_link_relay import SharedLinkRelay

pytestmark = pytest.mark.integration


def _wait(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def test_authenticated_control_and_jpeg_stream_share_relay(tmp_path, monkeypatch):
    from classes.parameters import Parameters

    monkeypatch.setattr(Parameters, "ENABLE_STREAMING", True)
    backend_listener = socket.socket()
    backend_listener.bind(("127.0.0.1", 0))
    backend_listener.listen(128)
    backend_port = backend_listener.getsockname()[1]
    app = create_app(port=backend_port, no_aircraft=True, mock_camera=True,
                     audit_path=tmp_path / "audit.jsonl")
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False,
                                            timeout_graceful_shutdown=1))
    backend_thread = threading.Thread(
        target=lambda: server.run(sockets=[backend_listener]), daemon=True)
    backend_thread.start()
    _wait(lambda: server.started)

    relay = SharedLinkRelay("127.0.0.1", backend_port,
                            uplink_bytes_per_second=128 * 1024,
                            downlink_bytes_per_second=128 * 1024,
                            latency_ms=8, chunk_bytes=1024)
    relay_ready = threading.Event()
    relay_stop = threading.Event()

    async def run_relay():
        await relay.start()
        relay_ready.set()
        await asyncio.to_thread(relay_stop.wait)
        await relay.close()

    relay_thread = threading.Thread(target=lambda: asyncio.run(run_relay()), daemon=True)
    relay_thread.start()
    _wait(relay_ready.is_set)
    relay_port = relay.port
    authority = f"127.0.0.1:{backend_port}"
    origin = f"http://127.0.0.1:{backend_port}"
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{relay_port}", timeout=5,
                          trust_env=False, headers={"Host": authority}) as client:
            login = client.post("/api/v1/auth/login",
                                json={"username": "operator", "password": "fixture-only"})
            assert login.status_code == 200, login.text
            csrf = login.json()["csrf_token"]
            session = client.cookies.get("pixeagle_session")
            assert session
            context = client.get("/api/v1/integration/context")
            assert context.status_code == 200
            guard = app.state.fixture_owner.app_controller.camera_runtime.guard()
            body = {
                "operation": "manual_begin", "gesture_id": "shared-link",
                "sequence": 0, "confirm": True,
                "idempotency_key": "shared-link-manual-begin",
                "camera_context": {"client_id": "shared-link", "guard": guard},
                "intent": {"axis": "pan", "value": 0.25},
            }
            relay_socket = socket.create_connection(("127.0.0.1", relay_port), timeout=5)
            sample_count = 60
            with connect(
                f"ws://127.0.0.1:{backend_port}/ws/video_feed",
                sock=relay_socket,
                origin=origin,
                additional_headers={"Cookie": f"pixeagle_session={session}"},
                proxy=None,
            ) as websocket:
                websocket.send(json.dumps({"type": "stream_capabilities", "latest_frame_ack": True,
                                           "delivery_token": "shared-link-token"}))
                metadata = json.loads(websocket.recv(timeout=5))
                jpeg = websocket.recv(timeout=5)
                assert isinstance(metadata, dict) and isinstance(jpeg, bytes)
                controls = []
                for sequence in range(sample_count):
                    operation = "manual_begin" if sequence == 0 else "manual_update"
                    body["operation"] = operation
                    body["sequence"] = sequence
                    body["idempotency_key"] = f"shared-link-{operation}-{sequence}"
                    control = client.post("/api/v1/actions/gimbal-control", json=body,
                                          headers={"x-pixeagle-csrf": csrf})
                    assert control.status_code == 202, control.text
                    controls.append(control)
                    if sequence < sample_count - 1:
                        websocket.send(json.dumps({
                            "type": "frame_ack", "frame_id": metadata["frame_id"],
                            "delivery_token": metadata.get("delivery_token", "shared-link-token"),
                        }))
                        metadata = json.loads(websocket.recv(timeout=5))
                        jpeg = websocket.recv(timeout=5)
                        assert isinstance(metadata, dict) and isinstance(jpeg, bytes)
                assert len(controls) == sample_count
                assert relay.metrics.chunks_upstream_to_client >= 1
                assert relay.metrics.chunks_client_to_upstream >= 1
                print("CAMERA_LINK " + json.dumps({
                    "scenario": "production_http_control_and_jpeg_websocket_shared_relay",
                    "control_statuses": [response.status_code for response in controls],
                    "control_updates": sample_count,
                    "video_frames_received": sample_count,
                    "uplink_bytes": relay.metrics.bytes_client_to_upstream,
                    "downlink_bytes": relay.metrics.bytes_upstream_to_client,
                    "latency_ms": 8,
                    "aggregate_budget_bytes_per_second": 128 * 1024,
                }, sort_keys=True))
    finally:
        relay_stop.set()
        relay_thread.join(timeout=3)
        assert not relay_thread.is_alive()
        server.should_exit = True
        backend_thread.join(timeout=3)
        backend_listener.close()
        assert not backend_thread.is_alive()
