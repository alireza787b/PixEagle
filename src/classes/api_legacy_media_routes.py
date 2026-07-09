"""Legacy media route helpers."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

from classes.api_auth_runtime import authorize_websocket_request
from classes.api_exposure_policy import (
    is_http_host_allowed,
    is_websocket_origin_allowed,
    is_websocket_request_allowed,
)
from classes.api_security_types import (
    APIAuditPolicy,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
)
from classes.parameters import Parameters


@dataclass
class ClientConnection:
    """Track legacy video WebSocket client connection state."""

    id: str
    connected_at: float
    last_frame_time: float
    quality: int
    frame_drops: int
    bandwidth_estimate: float
    frame_queue: deque[Any]
    websocket: Any = None
    principal: APIPrincipal | None = None


class SessionBoundStreamingResponse(StreamingResponse):
    """Streaming response that terminates when its browser session is revoked."""

    def __init__(
        self,
        content: Any,
        *,
        session_is_active: Callable[[], bool],
        on_session_revoked: Callable[[], None],
        poll_interval: float = 0.1,
        **kwargs: Any,
    ) -> None:
        super().__init__(content, **kwargs)
        self._session_is_active = session_is_active
        self._on_session_revoked = on_session_revoked
        self._session_poll_interval = max(0.01, float(poll_interval))

    async def _wait_for_session_revocation(self) -> None:
        while self._session_is_active():
            await asyncio.sleep(self._session_poll_interval)
        self._on_session_revoked()

    @staticmethod
    async def _cancel_task_bounded(task: asyncio.Future[Any]) -> None:
        if task.done():
            return
        task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True),
                timeout=1.0,
            )
        except asyncio.TimeoutError:
            pass

    async def _await_or_revoked(
        self,
        awaitable: Awaitable[Any],
        session_monitor: asyncio.Task[None],
    ) -> tuple[Any, bool]:
        operation = asyncio.ensure_future(awaitable)
        done, _ = await asyncio.wait(
            {operation, session_monitor},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if session_monitor in done:
            await self._cancel_task_bounded(operation)
            return None, True
        return operation.result(), False

    async def stream_response(self, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        session_monitor = asyncio.create_task(self._wait_for_session_revocation())
        iterator = self.body_iterator.__aiter__()
        revoked = False
        try:
            while True:
                try:
                    chunk, revoked = await self._await_or_revoked(
                        iterator.__anext__(),
                        session_monitor,
                    )
                except StopAsyncIteration:
                    break
                if revoked:
                    break
                if not isinstance(chunk, bytes | memoryview):
                    chunk = chunk.encode(self.charset)
                _, revoked = await self._await_or_revoked(
                    send(
                        {
                            "type": "http.response.body",
                            "body": chunk,
                            "more_body": True,
                        }
                    ),
                    session_monitor,
                )
                if revoked:
                    break
        finally:
            await self._cancel_task_bounded(session_monitor)
            close_iterator = getattr(iterator, "aclose", None)
            if close_iterator is not None:
                try:
                    await asyncio.wait_for(close_iterator(), timeout=1.0)
                except (asyncio.TimeoutError, RuntimeError):
                    pass

        try:
            await asyncio.wait_for(
                send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                        "more_body": False,
                    }
                ),
                timeout=1.0,
            )
        except (asyncio.TimeoutError, RuntimeError):
            if not revoked:
                raise


async def video_feed(handler: Any, request: Any):
    """Serve optimized legacy HTTP MJPEG streaming with adaptive quality."""
    if not getattr(Parameters, "ENABLE_STREAMING", True):
        raise HTTPException(status_code=503, detail="Streaming is disabled")

    client_id = f"http_{time.time()}"
    principal = getattr(request.state, "api_principal", APIPrincipal.anonymous())

    async with handler.connection_lock:
        if len(handler.http_connections) >= Parameters.HTTP_MAX_CONNECTIONS:
            raise HTTPException(status_code=503, detail="Max connections reached")
        handler.http_connections.add(client_id)
        handler._update_active_connection_count()

    handler.frame_publisher.register_client()
    handler.quality_engine.register_client(client_id, Parameters.STREAM_QUALITY)

    async def generate():
        """Frame generator using FramePublisher and AdaptiveQualityEngine."""
        quality = Parameters.STREAM_QUALITY
        last_send_time = 0.0
        last_frame_id = -1

        try:
            while not handler.is_shutting_down:
                current_time = time.time()

                remaining = handler.frame_interval - (current_time - last_send_time)
                if remaining > 0:
                    await asyncio.sleep(remaining)
                    continue

                stamped = handler.frame_publisher.get_latest(
                    prefer_osd=Parameters.STREAM_PROCESSED_OSD
                )
                if stamped is None:
                    await asyncio.sleep(0.01)
                    continue

                if stamped.frame_id == last_frame_id:
                    await asyncio.sleep(0.005)
                    continue

                try:
                    encode_start = time.monotonic()
                    frame_bytes = await handler.stream_optimizer.encode_frame_async(
                        stamped.frame,
                        stamped.frame_id,
                        quality,
                    )
                    encode_time = time.monotonic() - encode_start

                    if Parameters.ENABLE_ADAPTIVE_QUALITY:
                        quality = handler.quality_engine.report_frame_sent(
                            client_id,
                            len(frame_bytes),
                            encode_time,
                        )

                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: "
                        + str(len(frame_bytes)).encode()
                        + b"\r\n"
                        b"\r\n"
                        + frame_bytes
                        + b"\r\n"
                    )

                    last_send_time = time.time()
                    last_frame_id = stamped.frame_id
                    handler.stats["frames_sent"] += 1
                    handler.stats["total_bandwidth"] += len(frame_bytes)

                except Exception as exc:
                    handler.logger.error(f"Frame encoding error: {exc}")
                    handler.stats["frames_dropped"] += 1

        finally:
            handler.quality_engine.unregister_client(client_id)
            handler.frame_publisher.unregister_client()
            async with handler.connection_lock:
                handler.http_connections.discard(client_id)
                handler.stats["active_connections"] = len(
                    handler.http_connections
                ) + len(handler.ws_connections)

    response_kwargs = {
        "media_type": "multipart/x-mixed-replace; boundary=frame",
        "headers": {"Cache-Control": "no-cache"},
    }
    if principal.kind == APIPrincipalKind.SESSION:
        return SessionBoundStreamingResponse(
            generate(),
            session_is_active=lambda: handler._media_principal_is_active(principal),
            on_session_revoked=lambda: handler._record_media_session_revoked(
                principal=principal,
                transport="http",
                path="/video_feed",
            ),
            **response_kwargs,
        )
    return StreamingResponse(generate(), **response_kwargs)


async def video_feed_websocket_optimized(handler: Any, websocket: Any) -> None:
    """Serve optimized legacy WebSocket streaming with adaptive quality."""
    if not getattr(Parameters, "ENABLE_STREAMING", True):
        await websocket.close(code=1008, reason="Streaming is disabled")
        return

    if not _is_video_websocket_exposure_allowed(handler, websocket):
        handler._record_security_audit_event(
            event_type="api.websocket.origin",
            outcome="denied",
            reason="websocket_origin_not_allowed",
            transport="websocket",
            method="WEBSOCKET",
            path="/ws/video_feed",
            status_code=1008,
            principal=APIPrincipal.anonymous(),
            audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
            sensitivity=APISensitivity.MEDIA,
            client_host=getattr(getattr(websocket, "client", None), "host", None),
            host_header=websocket.headers.get("host"),
            origin=websocket.headers.get("origin"),
        )
        await websocket.close(code=1008, reason="WebSocket Host or Origin not allowed")
        return

    auth_runtime = getattr(handler, "api_auth_runtime", None)
    connection_principal = APIPrincipal.anonymous()
    if auth_runtime is not None:
        auth_result = authorize_websocket_request(
            runtime=auth_runtime,
            path="/ws/video_feed",
            headers=websocket.headers,
            client_host=getattr(getattr(websocket, "client", None), "host", None),
            host_header=websocket.headers.get("host"),
            exposure_policy=handler.exposure_policy,
            query_string=getattr(getattr(websocket, "url", None), "query", ""),
        )
        audit_ok = handler._record_security_audit_event(
            event_type="api.websocket.authorization",
            outcome="allowed" if auth_result.allowed else "denied",
            reason=auth_result.reason,
            transport="websocket",
            method="WEBSOCKET",
            path="/ws/video_feed",
            status_code=101 if auth_result.allowed else 1008,
            principal=auth_result.principal,
            audit_policy=auth_result.audit_policy,
            sensitivity=auth_result.sensitivity,
            client_host=getattr(getattr(websocket, "client", None), "host", None),
            host_header=websocket.headers.get("host"),
            origin=websocket.headers.get("origin"),
            missing_scopes=auth_result.missing_scopes,
        )
        if not audit_ok:
            await websocket.close(code=1011, reason="Security audit unavailable")
            return
        if not auth_result.allowed:
            await websocket.close(
                code=1008,
                reason="WebSocket API request not authorized",
            )
            return
        connection_principal = auth_result.principal

    await websocket.accept()
    client_id = f"ws_{id(websocket)}_{time.time()}"

    async with handler.connection_lock:
        if len(handler.ws_connections) >= Parameters.WS_MAX_CONNECTIONS:
            await websocket.close(code=1008, reason="Max connections reached")
            return

        handler.ws_connections[client_id] = ClientConnection(
            id=client_id,
            connected_at=time.time(),
            last_frame_time=0,
            quality=Parameters.STREAM_QUALITY,
            frame_drops=0,
            bandwidth_estimate=0,
            frame_queue=deque(maxlen=Parameters.MAX_FRAME_QUEUE),
            websocket=websocket,
            principal=connection_principal,
        )
        handler._update_active_connection_count()

    handler.frame_publisher.register_client()
    handler.quality_engine.register_client(client_id, Parameters.STREAM_QUALITY)
    handler.logger.info(f"WebSocket connected: {client_id}")

    try:
        client = handler.ws_connections.get(client_id)
        if client is None:
            return
        send_task = asyncio.create_task(handler._ws_send_frames(websocket, client))
        receive_task = asyncio.create_task(
            handler._ws_receive_messages(websocket, client)
        )
        session_task = asyncio.create_task(
            handler._ws_monitor_session(websocket, client)
        )

        done, pending = await asyncio.wait(
            [send_task, receive_task, session_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        if done:
            await asyncio.gather(*done, return_exceptions=True)

    except WebSocketDisconnect:
        handler.logger.info(f"WebSocket disconnected: {client_id}")
    except Exception as exc:
        handler.logger.error(f"WebSocket error: {exc}")
    finally:
        await handler._cleanup_websocket_client(client_id)


def _is_video_websocket_exposure_allowed(handler: Any, websocket: Any) -> bool:
    origin = websocket.headers.get("origin")
    auth_runtime = getattr(handler, "api_auth_runtime", None)
    allow_unauthenticated_media = bool(
        getattr(auth_runtime, "allow_unauthenticated_media_streaming", False)
    )

    if not allow_unauthenticated_media:
        return is_websocket_request_allowed(
            host=websocket.headers.get("host"),
            origin=origin,
            client_host=getattr(getattr(websocket, "client", None), "host", None),
            policy=handler.exposure_policy,
        )

    if not is_http_host_allowed(websocket.headers.get("host"), handler.exposure_policy):
        return False

    # Native media clients often omit Origin. Browser-origin requests still need
    # the explicit allowlist even in the unsafe lab-only media profile.
    if origin and not is_websocket_origin_allowed(origin, handler.exposure_policy):
        return False
    return True


async def get_streaming_status(handler: Any) -> JSONResponse:
    """Report current legacy streaming method, quality, and config state."""
    quality_states = handler.quality_engine.get_all_states()
    webrtc_count = (
        len(handler.webrtc_manager.peer_connections)
        if hasattr(handler.webrtc_manager, "peer_connections")
        else 0
    )

    gstreamer_info = None
    if (
        hasattr(handler.app_controller, "gstreamer_handler")
        and handler.app_controller.gstreamer_handler
    ):
        gstreamer_info = handler.app_controller.gstreamer_handler.encoder_status

    pipeline_metrics = getattr(handler.app_controller, "_pipeline_metrics", {})

    return JSONResponse(
        content={
            "active_method": (
                "webrtc"
                if webrtc_count > 0
                else (
                    "websocket"
                    if handler.ws_connections
                    else "http" if handler.http_connections else "none"
                )
            ),
            "http_clients": len(handler.http_connections),
            "websocket_clients": len(handler.ws_connections),
            "webrtc_clients": webrtc_count,
            "adaptive_quality_enabled": getattr(
                Parameters,
                "ENABLE_ADAPTIVE_QUALITY",
                True,
            ),
            "quality_engine": quality_states,
            "gstreamer": gstreamer_info,
            "pipeline": pipeline_metrics,
            "config": {
                "stream_fps": Parameters.STREAM_FPS,
                "stream_width": Parameters.STREAM_WIDTH,
                "stream_height": Parameters.STREAM_HEIGHT,
                "min_quality": getattr(Parameters, "MIN_QUALITY", 20),
                "max_quality": getattr(Parameters, "MAX_QUALITY", 95),
                "default_protocol": getattr(Parameters, "DEFAULT_PROTOCOL", "auto"),
                "pipeline_mode": getattr(Parameters, "PIPELINE_MODE", "REALTIME"),
            },
            "timestamp": time.time(),
        }
    )


async def get_streaming_stats(handler: Any) -> JSONResponse:
    """Get current legacy streaming statistics."""
    ws_clients_info = []
    async with handler.connection_lock:
        for client in handler.ws_connections.values():
            ws_clients_info.append(
                {
                    "id": client.id,
                    "connected_duration": time.time() - client.connected_at,
                    "quality": client.quality,
                    "frame_drops": client.frame_drops,
                    "bandwidth_kbps": client.bandwidth_estimate * 8 / 1024,
                }
            )

    osd_pipeline_stats = {}
    if hasattr(handler.app_controller, "osd_pipeline"):
        try:
            osd_pipeline_stats = handler.app_controller.osd_pipeline.get_stats()
        except Exception as exc:
            handler.logger.debug(f"Could not read OSD pipeline stats: {exc}")

    return JSONResponse(
        content={
            "frames_sent": handler.stats["frames_sent"],
            "frames_dropped": handler.stats["frames_dropped"],
            "total_bandwidth_mb": handler.stats["total_bandwidth"] / 1024 / 1024,
            "http_connections": len(handler.http_connections),
            "websocket_connections": len(handler.ws_connections),
            "websocket_clients": ws_clients_info,
            "cache_size": len(handler.stream_optimizer.frame_cache),
            "uptime": (
                time.time()
                - (handler.server.started if handler.server else time.time())
            ),
            "osd_pipeline": osd_pipeline_stats,
        }
    )


async def get_video_health(handler: Any) -> JSONResponse:
    """Get legacy video subsystem health for degraded-mode observability."""
    try:
        health = (
            handler.video_handler.get_connection_health()
            if handler.video_handler
            else {"status": "unavailable"}
        )
        smart = getattr(handler.app_controller, "smart_tracker", None)
        obb_health = {
            "model_loaded": bool(smart and hasattr(smart, "model")),
            "adapter_initialized": bool(smart and hasattr(smart, "last_detections")),
            "geometry_utils_available": bool(
                smart and hasattr(smart, "current_geometry_mode")
            ),
            "geometry_mode": getattr(smart, "current_geometry_mode", None),
            "model_task": getattr(smart, "model_task", None),
        }
        return JSONResponse(
            content={
                "success": True,
                "video": health,
                "obb_pipeline": obb_health,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error in get_video_health: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def reconnect_video(handler: Any) -> JSONResponse:
    """Manually trigger a legacy video reconnection attempt."""
    try:
        if not handler.video_handler:
            raise HTTPException(status_code=503, detail="Video handler not initialized")

        success = handler.video_handler.force_recovery()
        health = handler.video_handler.get_connection_health()

        return JSONResponse(
            content={
                "success": success,
                "message": (
                    "Video reconnect succeeded"
                    if success
                    else "Video reconnect attempted but source still unavailable"
                ),
                "video": health,
                "timestamp": time.time(),
            },
            status_code=200 if success else 503,
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error in reconnect_video: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
