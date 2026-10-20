#!/usr/bin/env python3
"""Loopback-only numbered-frame fixture for the native QGC presentation test.

Reuses the real authorization/signaling manager and sender. Only this fixture
admits the experimental provider before product qualification. No tracking or
aircraft API exists in this process, and it never reads deployment credentials.
"""

import argparse
import asyncio
import sys
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from classes.api_auth_runtime import APIAuthRuntime
from classes.api_exposure_policy import APIExposurePolicy
from classes.frame_publisher import CaptureStamp, FramePublisher
from classes.webrtc_manager import WebRTCManager


class QualificationManager(WebRTCManager):
    metadata_delay_seconds = 0.0

    @staticmethod
    def native_client_capabilities():
        return {"available": True}

    def get_browser_ice_servers(self):
        return []

    async def _send_signaling_message(self, websocket, payload, *, peer_id, phase):
        if payload.get("type") == "frame-context" and self.metadata_delay_seconds:
            await asyncio.sleep(self.metadata_delay_seconds)
        return await super()._send_signaling_message(websocket, payload, peer_id=peer_id, phase=phase)


def make_app(port: int, video: Path | None = None, *, metadata_delay_ms: int = 0) -> FastAPI:
    if not 0 <= metadata_delay_ms <= 250:
        raise ValueError("Metadata delay must be between zero and 250 milliseconds")
    publisher = FramePublisher()
    origin = f"http://127.0.0.1:{port}"
    policy = APIExposurePolicy(bind_host="127.0.0.1", mode="local_only",
                               cors_allowed_origins=(origin,), api_port=port)
    manager = QualificationManager(publisher, policy, APIAuthRuntime(mode="local_compat"))
    manager.metadata_delay_seconds = metadata_delay_ms / 1000

    first_frame = asyncio.Event()

    async def frames():
        capture_id = 0
        decoder = None
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qualification-file")

        def sample():
            nonlocal decoder, capture_id
            fps = 10.0
            if video is None:
                frame = np.full((120, 160, 3), 96, dtype=np.uint8)
            else:
                if decoder is None:
                    decoder = cv2.VideoCapture(str(video))
                    if not decoder.isOpened():
                        raise RuntimeError("Recorded fixture cannot be opened")
                fps = decoder.get(cv2.CAP_PROP_FPS) or 20.0
                ok, frame = decoder.read()
                if not ok:
                    decoder.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = decoder.read()
                if not ok:
                    raise RuntimeError("Recorded fixture cannot be decoded")
                height, width = frame.shape[:2]
                scale = min(1.0, 1280 / width, 720 / height)
                if scale < 1:
                    frame = cv2.resize(frame, (round(width * scale), round(height * scale)),
                                       interpolation=cv2.INTER_AREA)
            for bit in range(16):
                frame[:32, bit * 8:(bit + 1) * 8] = 225 if capture_id & (1 << bit) else 24
            height, width = frame.shape[:2]
            analysis = cv2.resize(frame, (max(1, width // 2), max(1, height // 2)), interpolation=cv2.INTER_AREA)
            publisher.publish(frame, frame, analysis_frame=analysis, target_revision="1",
                              capture=CaptureStamp("qualification-source", str(capture_id), time.monotonic(), "fresh"))
            capture_id = (capture_id + 1) % 65536
            return 1 / max(1.0, min(60.0, fps))

        loop = asyncio.get_running_loop()
        try:
            while True:
                started = loop.time()
                interval = await loop.run_in_executor(executor, sample)
                first_frame.set()
                await asyncio.sleep(max(0.0, interval - (loop.time() - started)))
        finally:
            if decoder is not None:
                await loop.run_in_executor(executor, decoder.release)
            executor.shutdown(wait=False, cancel_futures=True)

    @asynccontextmanager
    async def lifespan(_app):
        task = asyncio.create_task(frames())
        try:
            await asyncio.wait_for(first_frame.wait(), timeout=5)
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await manager.shutdown()

    app = FastAPI(lifespan=lifespan)

    @app.get("/qualification/context")
    async def context():
        stamped = publisher.get_latest(prefer_osd=True)
        provenance = stamped.provenance()
        return {
            "instance_id": provenance["instance_id"], "runtime_id": provenance["runtime_id"],
            "video": {key: provenance[key] for key in ("stream_id", "stream_epoch", "source_epoch", "variant")}
                     | {"width": stamped.frame.shape[1], "height": stamped.frame.shape[0],
                        "delivery_scaling_version": "1"},
        }

    @app.get("/qualification/selection/{token}")
    async def selected_frame(token: str):
        snapshot = publisher.selection_snapshot(token)
        if snapshot is None:
            return {"available": False}
        stamped = snapshot["stamped"]
        return {"available": True, "capture_id": stamped.capture.capture_id,
                "geometry": stamped.selection_geometry}

    @app.websocket("/ws/webrtc_signaling")
    async def signaling(websocket: WebSocket):
        await manager.signaling_handler(websocket)

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8197)
    parser.add_argument("--video", type=Path, help="Optional local recorded video; loops at its source cadence")
    parser.add_argument("--metadata-delay-ms", type=int, default=0, help="Fixture-only late frame-context delivery")
    args = parser.parse_args()
    if args.video is not None and not args.video.is_file():
        parser.error("--video must be an existing local file")
    uvicorn.run(make_app(args.port, args.video, metadata_delay_ms=args.metadata_delay_ms),
                host="127.0.0.1", port=args.port, access_log=False)
