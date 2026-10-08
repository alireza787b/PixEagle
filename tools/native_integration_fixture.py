#!/usr/bin/env python3
"""Loopback-only QGC validation fixture using real auth/integration routes.

Aircraft/tracker observations and camera pixels are synthetic. Auth, status,
publisher, JPEG encoding, and WebSocket routes are production implementations.
This does not construct AppController, MAVSDK, or a deployed runtime/service. Fixture
credentials are operator / fixture-only and have no use outside this process.
Run one process per endpoint; do not expose through a proxy or port forward.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from fastapi import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def create_app(*, port, system_id=None, uid=None, telemetry_uid=None, stale=False, audit_path,
               media_control_file=None, no_aircraft=False, mock_camera=False):
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from classes.aircraft_identity import canonical_uid
    from classes.api_auth_runtime import APIAuthRuntime, APIUserRecord, hash_password_pbkdf2_sha256
    from classes.api_exposure_policy import resolve_api_exposure_policy
    from classes.api_security_audit import APISecurityAuditLogger
    from classes import api_v1_contracts
    from classes.fastapi_api_v1_routes import API_V1_ROUTE_SPECS
    from classes.fastapi_handler import FastAPIHandler, StreamingOptimizer
    from classes.frame_publisher import FramePublisher
    from classes.adaptive_quality_engine import AdaptiveQualityEngine
    from classes.video_delivery_budget import VideoDeliveryBudget
    from classes.parameters import Parameters

    if not no_aircraft and (type(system_id) is not int or not 1 <= system_id <= 255 or canonical_uid(uid) is None):
        raise ValueError("Fixture requires a MAVLink system ID and nonzero uint64 UID")
    if no_aircraft and (system_id is not None or uid is not None or telemetry_uid is not None or stale):
        raise ValueError("No-aircraft mode cannot include synthetic aircraft observations")
    if telemetry_uid is not None and canonical_uid(telemetry_uid) is None:
        raise ValueError("Invalid telemetry UID")
    Parameters.USE_MAVLINK2REST = True
    state = {"connected": False}

    def command():
        return {"source": "mavsdk", "connected": state["connected"],
                "connection_generation": "1:1" if state["connected"] else "0:0",
                "system_id": None, "component_id": None,
                "autopilot_uid": canonical_uid(uid) if state["connected"] else None,
                "hardware_uid": None}

    def telemetry():
        if no_aircraft:
            return {"source": "mavlink2rest", "connected": False, "fresh": False,
                    "connection_generation": "0", "system_id": None, "component_id": None,
                    "autopilot_uid": None, "hardware_uid": None}
        return {"source": "mavlink2rest", "connected": True, "fresh": not stale,
                "connection_generation": "1", "system_id": system_id, "component_id": 1,
                "autopilot_uid": canonical_uid(telemetry_uid or uid), "hardware_uid": None}

    async def observe():
        await asyncio.sleep(0)
        if not no_aircraft:
            state["connected"] = True

    owner = FastAPIHandler.__new__(FastAPIHandler)
    owner.app_controller = SimpleNamespace(
        px4_interface=SimpleNamespace(get_aircraft_identity=command),
        mavlink_data_manager=SimpleNamespace(get_aircraft_identity=telemetry),
        observe_native_connection=observe,
        get_tracker_output=lambda: None,
        following_active=False, smart_mode_active=False, current_tracker_type="fixture_no_tracker",
    )
    owner.frame_publisher = FramePublisher()
    owner.stream_optimizer = StreamingOptimizer()
    owner.quality_engine = AdaptiveQualityEngine()
    owner.video_budget = VideoDeliveryBudget(getattr(Parameters, "STREAM_MAX_BITRATE_KBPS", 8000))
    owner.connection_lock = asyncio.Lock()
    owner.ws_connections = {}
    owner.http_connections = set()
    owner.stats = dict(frames_sent=0, frames_dropped=0, total_bandwidth=0, active_connections=0)
    owner.is_shutting_down = False
    owner.frame_interval = 0.1
    media = SyntheticMedia(owner.frame_publisher, system_id, media_control_file)

    if mock_camera:
        install_mock_camera(owner)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(media.run())
        try:
            yield
        finally:
            owner.is_shutting_down = True
            if mock_camera:
                owner.app_controller.camera_runtime.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await owner._close_all_websocket_clients(close_code=1001, close_reason="Fixture stopped")
            owner.stream_optimizer.encoder_pool.shutdown(wait=True)

    title = "PixEagle NO AIRCRAFT" if no_aircraft else "PixEagle MOCK AIRCRAFT"
    owner.app = FastAPI(title=f"{title} native integration fixture", lifespan=lifespan)
    owner.app.state.fixture_media = media
    owner.app.state.fixture_owner = owner
    owner.app.websocket("/ws/video_feed")(owner.video_feed_websocket_optimized)
    owner.logger = logging.getLogger("pixeagle.native_fixture")
    owner.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1", mode="local_only", api_port=port,
        cors_allowed_origins=[f"http://127.0.0.1:{port}"], allow_credentials=True,
    )
    user = APIUserRecord(username="operator", role="operator" if mock_camera else "viewer",
                         password_pbkdf2_sha256=hash_password_pbkdf2_sha256("fixture-only"))
    owner.api_auth_runtime = APIAuthRuntime(
        mode="browser_session", users_by_username={user.username: user},
        session_cookie_secure=False,
    )
    owner.security_audit_logger = APISecurityAuditLogger(log_path=Path(audit_path), enabled=True)
    owner.app.add_exception_handler(RequestValidationError, owner._handle_request_validation_error)
    owner._setup_middleware()
    handlers = {
        "get_auth_session", "login_auth_session", "logout_auth_session",
        "get_integration_context", "observe_integration_connection", "get_tracking_runtime_status",
    }
    if mock_camera:
        handlers.update({"get_gimbal_control_status", "gimbal_control_action",
                         "get_native_target_state", "get_tracking_catalog"})
    for spec in API_V1_ROUTE_SPECS:
        if spec.handler in handlers:
            owner.app.add_api_route(
                spec.path, getattr(owner, spec.handler), methods=[spec.method],
                response_model=getattr(api_v1_contracts, spec.response_model),
                responses=getattr(api_v1_contracts, spec.responses),
                operation_id=spec.operation_id, tags=list(spec.tags),
            )
    return owner.app



def install_mock_camera(owner):
    """Synthetic movement provider; it cannot create sockets or aircraft commands."""
    import threading
    from classes.camera_runtime import CameraRuntime
    from classes.gimbal_motion import SIP_MOTION_SETTINGS
    from classes.gimbal_types import TrackingState

    from classes.api_v1_native_targets import target_state
    from classes.api_v1_integration import integration_context
    from fastapi.responses import JSONResponse

    def fixture_response(response):
        if response.status_code != 200:
            return response
        payload = json.loads(response.body)
        payload["capabilities"] = [capability for capability in payload["capabilities"]
                                   if capability not in {"config.operations.v1", "models.operations.v1", "following.operations.v1"}]
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    async def fixture_context(http_request: Request):
        return fixture_response(await integration_context(owner, http_request))

    async def fixture_connection(http_request, request):
        return fixture_response(await integration_context(owner, http_request, connect=True))

    from classes.api_v1_contracts import APIIntegrationConnectionRequest
    fixture_connection.__annotations__ = {"http_request": Request, "request": APIIntegrationConnectionRequest}

    async def fixture_targets(http_request: Request):
        payload = target_state(owner, http_request.state.api_principal)
        payload["allowed_actions"] = []
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    owner.get_integration_context = fixture_context
    owner.observe_integration_connection = fixture_connection
    owner.get_native_target_state = fixture_targets
    owner._native_smart_availability = {"available": False, "reason": "This fixture provides camera movement only."}
    owner._native_smart_checked_at = float("inf")
    runtime_status = dict(status="no_output", consumer_guidance="no_output", has_output=False,
                          active_tracking=False, usable_for_following=False, data_is_stale=False,
                          configured_tracker="CSRT", active_tracker="CSRT", timestamp=time.time())
    owner._get_tracking_catalog_snapshot = lambda: dict(
        status="available", consumer_guidance="selectable", configured_tracker="CSRT", active_tracker="CSRT",
        ui_trackers=[dict(name="CSRT", display_name="CSRT (mock fixture)", factory_key="CSRT",
                         request_tracker_type="CSRT", source="builtin_compatibility")],
        tracker_types={}, runtime_status=runtime_status, timestamp=time.time())

    app = owner.app_controller
    app.current_tracker_type = "CSRT"
    app.frame_publisher = owner.frame_publisher
    app._follower_state_lock = asyncio.Lock()
    app._tracker_model_state_lock = threading.RLock()
    app._tracking_session_generation = 0
    app.tracker = SimpleNamespace(is_external_tracker=False)
    app.fixture_camera_commands = []
    app.video_handler = SimpleNamespace(selection_source={})
    app._advance_tracking_session_generation = lambda: setattr(
        app, "_tracking_session_generation", app._tracking_session_generation + 1)

    async def run(operation):
        return await operation()
    app._run_on_flight_event_loop = run

    class MockControl:
        capabilities = ("pan", "tilt", "roll", "zoom", "home", "stop")
        motion_settings = SIP_MOTION_SETTINGS
        selection_mode = "classic"

        def stop(self):
            app.fixture_camera_commands.append({"operation": "stop", "mock": True})
            return True

        def close(self):
            self.stop()

        async def prepare_manual(self, command_guard):
            with command_guard():
                pass

        def send_manual_intent(self, axis, value):
            app.fixture_camera_commands.append({"operation": axis, "value": value, "mock": True})

        async def execute(self, operation, **fields):
            guard = fields.get("selection_guard")
            if guard is not None:
                with guard():
                    pass
            app.fixture_camera_commands.append({"operation": operation, "mock": True})
            if operation in {"pan", "tilt", "roll", "zoom"}:
                await asyncio.sleep(min(fields.get("duration_ms") or 250, 1000) / 1000)
                self.stop()
            return {"success": True, "message": "Mock camera command observed; no hardware IO."}

    provider = SimpleNamespace(
        provider_id="fixture_camera", running=True, manual_control=MockControl(),
        selection_modes=lambda: [], matches_video_source=lambda source: False,
        get_current_data=lambda: SimpleNamespace(
            angles=SimpleNamespace(yaw=12.5, pitch=-8.0, roll=2.0, timestamp=datetime.now(),
                                   coordinate_system=SimpleNamespace(value="gimbal_body")),
            tracking_status=SimpleNamespace(state=TrackingState.DISABLED)),
        stop_listening=lambda: None,
    )
    app.camera_runtime = CameraRuntime(app, {"ENABLED": True, "CONTROL_ENABLED": True})
    app.camera_runtime.provider = provider
    app.camera_runtime.start()


class SyntheticMedia:
    """Numbered pixels through the production publisher; local file controls only.

    Controls: mode=live|freeze|drop, source=<label>, reset=<marker>, width/height,
    variant=processed_osd|raw. Replace the JSON file atomically. Invalid controls
    stop publication until repaired. Freeze republishes cached pixels with their
    original capture time/id; drop publishes nothing. Source/reset retires old
    publication epochs. No camera, target, or flight operations are available.
    """

    def __init__(self, publisher, system_id, control_file=None):
        self.publisher = publisher
        self.system_id = system_id
        self.control_file = Path(control_file) if control_file else None
        self.source = None
        self.reset_marker = None
        self.source_epoch = None
        self.number = 0
        self.pixels = None
        self.captured_at = None
        self.format = None

    def controls(self):
        control = json.loads(self.control_file.read_text()) if self.control_file and self.control_file.exists() else {}
        allowed = {"mode", "source", "reset", "width", "height", "variant"}
        if not isinstance(control, dict) or set(control) - allowed:
            raise ValueError("Unknown synthetic-media control")
        control = {"mode": "live", "source": "camera-a", "reset": "0",
                   "width": 640, "height": 360, "variant": "processed_osd", **control}
        if control["mode"] not in ("live", "freeze", "drop"):
            raise ValueError("Invalid mode")
        if control["variant"] not in ("raw", "processed_osd"):
            raise ValueError("Invalid variant")
        for name in ("source", "reset"):
            if not isinstance(control[name], str) or not 1 <= len(control[name]) <= 80:
                raise ValueError("Invalid source/reset marker")
        for name in ("width", "height"):
            if type(control[name]) is not int or not 240 <= control[name] <= 1920:
                raise ValueError("Invalid dimensions")
        return control

    def step(self):
        import cv2
        import numpy as np
        from classes.frame_publisher import CaptureStamp
        control = self.controls()
        if self.source != control["source"]:
            self.source = control["source"]
            self.source_epoch = str(uuid.uuid4())
            self.publisher.invalidate_source(self.source_epoch)
            self.pixels = None
            self.number = 0
        if self.reset_marker != control["reset"]:
            self.reset_marker = control["reset"]
            self.publisher.invalidate_source(self.source_epoch)
        dimensions = (control["width"], control["height"], control["variant"])
        if self.format != dimensions:
            self.format = dimensions
            self.pixels = None
            self.publisher.invalidate_source(self.source_epoch)
        if control["mode"] == "drop":
            return
        cached = control["mode"] == "freeze" and self.pixels is not None
        if not cached:
            self.number += 1
            self.captured_at = time.monotonic()
            width, height, _ = dimensions
            self.pixels = np.full((height, width, 3), (48, 32, 24), dtype=np.uint8)
            # 64-bit capture ID, little-endian bit order in an 8x8 grid;
            # 12px cells at (16,16), robust to normal JPEG compression.
            for bit in range(64):
                x, y = 16 + (bit % 8) * 12, 16 + (bit // 8) * 12
                value = 255 if self.number & (1 << bit) else 0
                self.pixels[y:y + 12, x:x + 12] = value
            cv2.putText(self.pixels, f"FRAME {self.number}", (125, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
            aircraft_label = "NO AIRCRAFT" if self.system_id is None else f"MOCK SYS {self.system_id}"
            cv2.putText(self.pixels, aircraft_label, (125, 78),
                        cv2.FONT_HERSHEY_SIMPLEX, .55, (160, 220, 255), 1)
            cv2.putText(self.pixels, self.source, (16, height - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 220, 160), 1)
        capture = CaptureStamp(self.source_epoch, str(self.number), self.captured_at,
                               "cached" if cached else "fresh")
        is_osd = control["variant"] == "processed_osd"
        self.publisher.publish(self.pixels if is_osd else None,
                               None if is_osd else self.pixels, capture=capture)

    async def run(self):
        while True:
            try:
                self.step()
            except (ValueError, OSError):
                pass  # Invalid/partial fixture controls freeze publication, never live media.
            await asyncio.sleep(.1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--system-id", type=int)
    parser.add_argument("--uid")
    parser.add_argument("--no-aircraft", action="store_true",
                        help="Video/status only; command and telemetry remain disconnected")
    parser.add_argument("--mock-camera", action="store_true", help="Synthetic camera controls, no sockets or hardware")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--telemetry-uid", help="Simulate an identity mismatch")
    parser.add_argument("--media-control-file", type=Path, help="Local synthetic-media JSON controls (no HTTP control API)")
    parser.add_argument("--stale", action="store_true", help="Simulate stale telemetry")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Fixture port must be 1024–65535")
    if args.no_aircraft:
        if args.system_id is not None or args.uid is not None or args.telemetry_uid is not None or args.stale:
            parser.error("--no-aircraft cannot be combined with aircraft identity or freshness options")
    elif args.system_id is None or args.uid is None:
        parser.error("Use --system-id and --uid, or --no-aircraft")
    os.environ["PIXEAGLE_INSTANCE_ID"] = args.instance_id
    import uvicorn

    with tempfile.TemporaryDirectory(prefix="pixeagle-native-fixture-") as directory:
        app = create_app(port=args.port, system_id=args.system_id, uid=args.uid,
                         telemetry_uid=args.telemetry_uid, stale=args.stale,
                         audit_path=Path(directory) / "security-audit.jsonl",
                         media_control_file=args.media_control_file, no_aircraft=args.no_aircraft,
                         mock_camera=args.mock_camera)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
