#!/usr/bin/env python3
"""Probe the running Windows Core preview, including decoded video transports."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from PIL import Image, UnidentifiedImageError


JPEG_START = b"\xff\xd8"
JPEG_END = b"\xff\xd9"


class SmokeError(RuntimeError):
    """Raised when a Windows Core runtime postcondition is not observed."""


def _decode_jpeg(payload: bytes, label: str) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(payload)) as image:
            if image.format != "JPEG":
                raise SmokeError(f"{label} payload is not a JPEG image")
            image.load()
            width, height = int(image.width), int(image.height)
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise SmokeError(f"{label} JPEG payload could not be decoded: {exc}") from exc
    if width <= 0 or height <= 0:
        raise SmokeError(f"{label} JPEG has invalid dimensions")
    return width, height


def _http_get(url: str, timeout: float) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return (
                int(response.status),
                response.read(256 * 1024),
                str(response.headers.get("content-type", "")),
            )
    except (OSError, urllib.error.URLError) as exc:
        raise SmokeError(f"HTTP probe failed for {url}: {exc}") from exc


def _probe_json_status(url: str, timeout: float) -> None:
    status, body, content_type = _http_get(url, timeout)
    if status != 200:
        raise SmokeError(f"backend status returned HTTP {status}")
    try:
        payload = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SmokeError("backend status did not return JSON") from exc
    if not isinstance(payload, dict):
        raise SmokeError("backend status payload is not an object")
    if "json" not in content_type.lower():
        raise SmokeError(f"backend status content type is not JSON: {content_type}")


def _probe_dashboard(url: str, timeout: float) -> None:
    status, body, content_type = _http_get(url, timeout)
    if status != 200:
        raise SmokeError(f"dashboard returned HTTP {status}")
    lowered = body.lower()
    if b"<html" not in lowered and b"<!doctype html" not in lowered:
        raise SmokeError("dashboard response is not HTML")
    if "html" not in content_type.lower():
        raise SmokeError(f"dashboard content type is not HTML: {content_type}")


def _probe_http_jpeg(url: str, timeout: float) -> tuple[int, int]:
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    try:
        with urllib.request.urlopen(url, timeout=min(timeout, 5.0)) as response:
            content_type = str(response.headers.get("content-type", "")).lower()
            if "multipart" not in content_type:
                raise SmokeError(
                    f"HTTP video feed is not multipart MJPEG: {content_type}"
                )
            while time.monotonic() < deadline and len(buffer) < 4 * 1024 * 1024:
                chunk = response.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)
                start = buffer.find(JPEG_START)
                end = buffer.find(JPEG_END, start + 2) if start >= 0 else -1
                if start >= 0 and end > start:
                    return _decode_jpeg(
                        bytes(buffer[start : end + len(JPEG_END)]),
                        "HTTP",
                    )
    except (OSError, urllib.error.URLError) as exc:
        raise SmokeError(f"HTTP JPEG probe failed: {exc}") from exc
    raise SmokeError("HTTP JPEG feed did not deliver a complete JPEG frame")


async def _probe_websocket_jpeg(url: str, timeout: float) -> tuple[int, int]:
    deadline = asyncio.get_running_loop().time() + timeout
    metadata_seen = False
    try:
        async with websockets.connect(
            url,
            open_timeout=min(timeout, 10.0),
            close_timeout=2.0,
            max_size=4 * 1024 * 1024,
        ) as websocket:
            while asyncio.get_running_loop().time() < deadline:
                remaining = deadline - asyncio.get_running_loop().time()
                message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                if isinstance(message, str):
                    try:
                        payload = json.loads(message)
                    except json.JSONDecodeError:
                        continue
                    metadata_seen = (
                        isinstance(payload, dict) and payload.get("type") == "frame"
                    ) or metadata_seen
                    continue
                if (
                    metadata_seen
                    and isinstance(message, bytes)
                    and message.startswith(JPEG_START)
                    and message.endswith(JPEG_END)
                ):
                    return _decode_jpeg(message, "WebSocket")
    except (OSError, TimeoutError, websockets.WebSocketException) as exc:
        raise SmokeError(f"WebSocket JPEG probe failed: {exc}") from exc
    raise SmokeError("WebSocket JPEG feed did not deliver metadata plus a JPEG frame")


def _decode_ice_candidate(payload: Any):
    if not isinstance(payload, dict):
        return None
    candidate_payload = payload.get("candidate", payload)
    if not isinstance(candidate_payload, dict):
        return None
    candidate_text = str(candidate_payload.get("candidate", "")).strip()
    if not candidate_text:
        return None
    if candidate_text.startswith("candidate:"):
        candidate_text = candidate_text[len("candidate:") :]
    candidate = candidate_from_sdp(candidate_text)
    candidate.sdpMid = candidate_payload.get("sdpMid")
    candidate.sdpMLineIndex = candidate_payload.get("sdpMLineIndex")
    return candidate


async def _probe_webrtc(url: str, timeout: float) -> tuple[int, int]:
    peer = RTCPeerConnection()
    peer.addTransceiver("video", direction="recvonly")
    loop = asyncio.get_running_loop()
    frame_result: asyncio.Future[tuple[int, int]] = loop.create_future()
    track_tasks: list[asyncio.Task[Any]] = []
    pending_candidates: list[Any] = []

    @peer.on("track")
    def on_track(track) -> None:
        if track.kind != "video":
            return

        async def receive_frame() -> None:
            try:
                frame = await track.recv()
                if not frame_result.done():
                    frame_result.set_result((int(frame.width), int(frame.height)))
            except Exception as exc:
                if not frame_result.done():
                    frame_result.set_exception(
                        SmokeError(f"WebRTC video track failed: {exc}")
                    )

        track_tasks.append(asyncio.create_task(receive_frame()))

    signaling_task: asyncio.Task[Any] | None = None
    try:
        async with websockets.connect(
            url,
            open_timeout=min(timeout, 10.0),
            close_timeout=2.0,
            max_size=4 * 1024 * 1024,
        ) as websocket:
            offer = await peer.createOffer()
            await peer.setLocalDescription(offer)
            local = peer.localDescription or offer
            await websocket.send(
                json.dumps(
                    {
                        "type": "offer",
                        "payload": {"sdp": local.sdp, "type": local.type},
                    }
                )
            )

            async def consume_signaling() -> None:
                async for raw in websocket:
                    if not isinstance(raw, str):
                        continue
                    message = json.loads(raw)
                    message_type = message.get("type")
                    if message_type == "answer":
                        payload = message.get("payload")
                        if not isinstance(payload, dict):
                            raise SmokeError("WebRTC answer payload is invalid")
                        await peer.setRemoteDescription(
                            RTCSessionDescription(
                                sdp=str(payload.get("sdp", "")),
                                type=str(payload.get("type", "")),
                            )
                        )
                        while pending_candidates:
                            await peer.addIceCandidate(pending_candidates.pop(0))
                    elif message_type == "ice-candidate":
                        candidate = _decode_ice_candidate(message.get("payload"))
                        if candidate is None:
                            continue
                        if peer.remoteDescription is None:
                            pending_candidates.append(candidate)
                        else:
                            await peer.addIceCandidate(candidate)
                    elif message_type == "error":
                        raise SmokeError(
                            "WebRTC signaling error: "
                            f"{message.get('message', 'unknown error')}"
                        )

            signaling_task = asyncio.create_task(consume_signaling())
            done, _pending = await asyncio.wait(
                {frame_result, signaling_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if frame_result in done:
                width, height = frame_result.result()
                if width <= 0 or height <= 0:
                    raise SmokeError("WebRTC delivered an invalid video frame")
                return width, height
            if signaling_task in done:
                signaling_task.result()
                raise SmokeError("WebRTC signaling closed before a video frame arrived")
            raise SmokeError("WebRTC did not deliver a decoded frame before timeout")
    except (OSError, TimeoutError, websockets.WebSocketException) as exc:
        raise SmokeError(f"WebRTC probe failed: {exc}") from exc
    finally:
        if signaling_task is not None and not signaling_task.done():
            signaling_task.cancel()
            await asyncio.gather(signaling_task, return_exceptions=True)
        for task in track_tasks:
            if not task.done():
                task.cancel()
        if track_tasks:
            await asyncio.gather(*track_tasks, return_exceptions=True)
        await peer.close()


async def _run(args: argparse.Namespace) -> None:
    backend = f"http://{args.host}:{args.backend_port}"
    dashboard = f"http://{args.host}:{args.dashboard_port}"
    websocket = f"ws://{args.host}:{args.backend_port}"

    await asyncio.to_thread(
        _probe_json_status,
        f"{backend}/status",
        args.timeout,
    )
    print("[OK] backend status")
    await asyncio.to_thread(_probe_dashboard, dashboard, args.timeout)
    print("[OK] dashboard HTML")
    http_width, http_height = await asyncio.to_thread(
        _probe_http_jpeg,
        f"{backend}/video_feed",
        args.timeout,
    )
    print(f"[OK] HTTP JPEG decoded frame ({http_width}x{http_height})")
    ws_width, ws_height = await _probe_websocket_jpeg(
        f"{websocket}/ws/video_feed",
        args.timeout,
    )
    print(f"[OK] WebSocket JPEG decoded frame ({ws_width}x{ws_height})")
    width, height = await _probe_webrtc(
        f"{websocket}/ws/webrtc_signaling",
        args.timeout,
    )
    print(f"[OK] WebRTC decoded frame ({width}x{height})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe a running local PixEagle Windows Core preview",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=5077)
    parser.add_argument("--dashboard-port", type=int, default=3040)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("[ERROR] Windows Core smoke probes are loopback-only")
        return 2
    if not 5.0 <= args.timeout <= 120.0:
        print("[ERROR] --timeout must be between 5 and 120 seconds")
        return 2
    try:
        asyncio.run(_run(args))
    except (SmokeError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
