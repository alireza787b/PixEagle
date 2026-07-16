# src/classes/webrtc_manager.py
"""
WebRTC peer connection manager with signaling over WebSocket.

Uses FramePublisher for thread-safe frame access (instead of direct
video_handler.get_frame() which bypassed OSD/resize and competed
with the main capture loop).
"""

from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.sdp import candidate_from_sdp
from av import VideoFrame
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
import fractions
import secrets
import time
from typing import Any, Dict

from classes.api_auth_runtime import APIAuthRuntime, authorize_websocket_request
from classes.api_exposure_policy import is_websocket_request_allowed
from classes.api_security_audit import APISecurityAuditError, audit_failure_must_block
from classes.api_security_types import (
    APIAuditPolicy,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
)
from classes.parameters import Parameters

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class VideoStreamTrackCustom(VideoStreamTrack):
    """
    A video stream track that pulls frames from FramePublisher.

    Fixes from original:
    - Uses FramePublisher instead of video_handler.get_frame() (no capture device contention)
    - PTS is monotonic milliseconds from stream start (not Unix timestamp)
    - Reads OSD-composited, stream-resolution frames
    """

    def __init__(self, frame_publisher, frame_rate=30):
        super().__init__()
        self.frame_publisher = frame_publisher
        self.frame_rate = frame_rate
        self.frame_interval = 1.0 / self.frame_rate
        self.last_frame_time = time.time()
        self._start_time = time.monotonic()

    async def recv(self):
        """Receive the next video frame."""
        while True:
            current_time = time.time()
            elapsed = current_time - self.last_frame_time

            if elapsed < self.frame_interval:
                await asyncio.sleep(self.frame_interval - elapsed)

            stamped = self.frame_publisher.get_latest(prefer_osd=True)
            if stamped is not None:
                frame = stamped.frame
                # Validate frame format
                if frame.dtype != 'uint8' or len(frame.shape) != 3 or frame.shape[2] != 3:
                    logger.error("Invalid frame format. Expected uint8 with 3 channels (BGR).")
                    await asyncio.sleep(0.01)
                    continue

                try:
                    video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
                    # Correct PTS: monotonic counter in milliseconds from stream start
                    elapsed_ms = int((time.monotonic() - self._start_time) * 1000)
                    video_frame.pts = elapsed_ms
                    video_frame.time_base = fractions.Fraction(1, 1000)
                    self.last_frame_time = current_time
                    return video_frame
                except Exception as e:
                    logger.error(f"Error converting frame to VideoFrame: {e}")
                    await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(0.01)


class WebRTCManager:
    """
    Manages WebRTC peer connections and signaling.

    Accepts a FramePublisher instead of VideoHandler for thread-safe
    frame access. Enforces connection limits via WEBRTC_MAX_CONNECTIONS.
    """

    def __init__(
        self,
        frame_publisher,
        exposure_policy,
        api_auth_runtime=None,
        security_audit_logger=None,
    ):
        """
        Initialize the WebRTCManager.

        Args:
            frame_publisher: A FramePublisher instance for thread-safe frame access.
            exposure_policy: Validated HTTP/WebSocket exposure policy.
            api_auth_runtime: Shared API authentication runtime.
            security_audit_logger: Durable security audit logger.
        """
        self.frame_publisher = frame_publisher
        self.exposure_policy = exposure_policy
        self.api_auth_runtime: APIAuthRuntime | None = api_auth_runtime
        self.security_audit_logger = security_audit_logger
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.max_connections = getattr(Parameters, 'WEBRTC_MAX_CONNECTIONS', 3)
        self.rtc_configuration, self.ice_server_summary = self._build_rtc_configuration()
        self._signaling_capacity_lock = asyncio.Lock()
        self._active_signaling_sessions = 0
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    @staticmethod
    def _build_rtc_configuration() -> tuple[RTCConfiguration, list[dict[str, Any]]]:
        """Build server-side ICE configuration without exposing TURN secrets."""
        ice_servers = []
        summary = []

        stun_url = str(getattr(Parameters, "WEBRTC_STUN_SERVER", "") or "").strip()
        if stun_url:
            if stun_url.lower().startswith(("stun:", "stuns:")):
                ice_servers.append(RTCIceServer(urls=stun_url))
                summary.append({"kind": "stun", "url": stun_url, "configured": True})
            else:
                logger.error("Ignoring WEBRTC_STUN_SERVER with unsupported scheme")
                summary.append({"kind": "stun", "url": None, "configured": False})

        turn_url = str(getattr(Parameters, "WEBRTC_TURN_SERVER", "") or "").strip()
        turn_username = str(
            getattr(Parameters, "WEBRTC_TURN_USERNAME", "") or ""
        ).strip()
        turn_credential = str(
            getattr(Parameters, "WEBRTC_TURN_CREDENTIAL", "") or ""
        )
        if turn_url:
            valid_scheme = turn_url.lower().startswith(("turn:", "turns:"))
            complete_credentials = bool(turn_username) == bool(turn_credential)
            if valid_scheme and complete_credentials:
                ice_servers.append(
                    RTCIceServer(
                        urls=turn_url,
                        username=turn_username or None,
                        credential=turn_credential or None,
                    )
                )
                summary.append(
                    {
                        "kind": "turn",
                        "url": turn_url,
                        "configured": True,
                        "credentials_configured": bool(turn_username),
                    }
                )
            else:
                logger.error(
                    "Ignoring invalid WEBRTC_TURN_SERVER configuration: "
                    "require a turn:/turns: URL and both or neither credential fields"
                )
                summary.append(
                    {
                        "kind": "turn",
                        "url": None,
                        "configured": False,
                        "credentials_configured": False,
                    }
                )

        return RTCConfiguration(iceServers=ice_servers), summary

    def _create_peer_connection(self) -> RTCPeerConnection:
        """Create a peer using configured ICE servers when initialized normally."""
        configuration = getattr(self, "rtc_configuration", None)
        if configuration is None:
            return RTCPeerConnection()
        return RTCPeerConnection(configuration=configuration)

    def _record_security_audit_event(
        self,
        *,
        event_type,
        outcome,
        reason,
        websocket,
        status_code,
        principal,
        audit_policy,
        sensitivity,
        missing_scopes=(),
    ) -> bool:
        audit_logger = getattr(self, "security_audit_logger", None)
        if audit_logger is None:
            return True
        try:
            recorded = audit_logger.record_event(
                event_type=event_type,
                outcome=outcome,
                reason=reason,
                transport="websocket",
                method="WEBSOCKET",
                path="/ws/webrtc_signaling",
                status_code=status_code,
                principal=principal,
                audit_policy=audit_policy,
                sensitivity=sensitivity,
                client_host=getattr(getattr(websocket, "client", None), "host", None),
                host_header=websocket.headers.get("host"),
                origin=websocket.headers.get("origin"),
                missing_scopes=missing_scopes,
            )
            if recorded:
                return True
            return not audit_failure_must_block(
                audit_policy=audit_policy,
                outcome=outcome,
            )
        except APISecurityAuditError as exc:
            self.logger.error("API security audit write failed: %s", exc)
            return not audit_failure_must_block(
                audit_policy=audit_policy,
                outcome=outcome,
            )

    async def signaling_handler(self, websocket: WebSocket):
        """
        Handle incoming signaling messages over WebSocket.

        One peer connection per WebSocket session. A server-owned peer_id is
        assigned on the first message and reused for all subsequent messages
        on the same connection.
        """
        if not getattr(Parameters, "ENABLE_STREAMING", True):
            await websocket.close(code=1008, reason="Streaming is disabled")
            return

        if not is_websocket_request_allowed(
            host=websocket.headers.get("host"),
            origin=websocket.headers.get("origin"),
            client_host=getattr(getattr(websocket, "client", None), "host", None),
            policy=self.exposure_policy,
        ):
            self._record_security_audit_event(
                event_type="api.websocket.origin",
                outcome="denied",
                reason="websocket_origin_not_allowed",
                websocket=websocket,
                status_code=1008,
                principal=APIPrincipal.anonymous(),
                audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
                sensitivity=APISensitivity.MEDIA,
            )
            await websocket.close(code=1008, reason="WebSocket Host or Origin not allowed")
            return
        auth_runtime = getattr(self, "api_auth_runtime", None)
        connection_principal = APIPrincipal.anonymous()
        if auth_runtime is not None:
            auth_result = authorize_websocket_request(
                runtime=auth_runtime,
                path="/ws/webrtc_signaling",
                headers=websocket.headers,
                client_host=getattr(getattr(websocket, "client", None), "host", None),
                host_header=websocket.headers.get("host"),
                exposure_policy=self.exposure_policy,
                query_string=getattr(getattr(websocket, "url", None), "query", ""),
            )
            audit_ok = self._record_security_audit_event(
                event_type="api.websocket.authorization",
                outcome="allowed" if auth_result.allowed else "denied",
                reason=auth_result.reason,
                websocket=websocket,
                status_code=101 if auth_result.allowed else 1008,
                principal=auth_result.principal,
                audit_policy=auth_result.audit_policy,
                sensitivity=auth_result.sensitivity,
                missing_scopes=auth_result.missing_scopes,
            )
            if not audit_ok:
                await websocket.close(code=1011, reason="Security audit unavailable")
                return
            if not auth_result.allowed:
                await websocket.close(code=1008, reason="WebSocket API request not authorized")
                return
            connection_principal = auth_result.principal
        await websocket.accept()
        if not await self._reserve_signaling_slot():
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Max WebRTC connections ({self.max_connections}) reached"
            }))
            await websocket.close(code=1008, reason="Max connections reached")
            return

        try:
            state = {"peer_id": None, "registered": False}
            session_monitor = asyncio.create_task(
                self._monitor_session(websocket, connection_principal)
            )
            message_task = asyncio.create_task(
                self._consume_signaling_messages(websocket, state)
            )
            try:
                done, pending = await asyncio.wait(
                    {message_task, session_monitor},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                results = await asyncio.gather(
                    *done,
                    *pending,
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, WebSocketDisconnect):
                        self.logger.info(
                            "WebRTC signaling WebSocket disconnected: %s",
                            state["peer_id"],
                        )
                    elif isinstance(result, Exception) and not isinstance(
                        result,
                        asyncio.CancelledError,
                    ):
                        self.logger.error("Error in signaling_handler: %s", result)
            finally:
                for task in (message_task, session_monitor):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(
                    message_task,
                    session_monitor,
                    return_exceptions=True,
                )
                peer_id = state["peer_id"]
                if peer_id:
                    await self._cleanup_peer(peer_id)
                elif state["registered"]:
                    # Edge case: registered but peer_id somehow lost
                    self.frame_publisher.unregister_client()
        finally:
            await self._release_signaling_slot()

    async def _reserve_signaling_slot(self) -> bool:
        """Atomically reserve capacity for one accepted signaling session."""
        lock = getattr(self, "_signaling_capacity_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._signaling_capacity_lock = lock
        async with lock:
            active = getattr(self, "_active_signaling_sessions", 0)
            if active >= self.max_connections:
                return False
            self._active_signaling_sessions = active + 1
            return True

    async def _release_signaling_slot(self) -> None:
        """Release a signaling-session capacity reservation."""
        lock = getattr(self, "_signaling_capacity_lock", None)
        if lock is None:
            self._active_signaling_sessions = 0
            return
        async with lock:
            active = getattr(self, "_active_signaling_sessions", 0)
            self._active_signaling_sessions = max(0, active - 1)

    async def _consume_signaling_messages(
        self,
        websocket: WebSocket,
        state: Dict[str, Any],
    ) -> None:
        """Consume signaling messages until disconnect or task cancellation."""
        async for message in websocket.iter_text():
            data = json.loads(message)
            msg_type = data.get("type")
            payload = data.get("payload")

            peer_id = state["peer_id"]
            if peer_id is None:
                peer_id = self._new_peer_id()
                state["peer_id"] = peer_id
                self.peer_connections[peer_id] = self._create_peer_connection()
                self.frame_publisher.register_client()
                state["registered"] = True
                self.logger.info(f"Created RTCPeerConnection for {peer_id}")

                @self.peer_connections[peer_id].on("icecandidate")
                async def on_icecandidate(event, _peer_id=peer_id):
                    if event.candidate:
                        try:
                            await websocket.send_text(json.dumps({
                                "type": "ice-candidate",
                                "peer_id": _peer_id,
                                "payload": {
                                    "candidate": event.candidate.to_json()
                                }
                            }))
                            self.logger.debug(f"Sent ICE candidate to {_peer_id}")
                        except Exception:
                            pass

                @self.peer_connections[peer_id].on("connectionstatechange")
                async def on_connectionstatechange(_peer_id=peer_id):
                    pc = self.peer_connections.get(_peer_id)
                    if pc:
                        connection_state = pc.connectionState
                        self.logger.info(
                            "Connection state for %s: %s",
                            _peer_id,
                            connection_state,
                        )
                        if connection_state in ("failed", "closed"):
                            await self._cleanup_peer(_peer_id)

            pc = self.peer_connections.get(peer_id)
            if not pc:
                self.logger.error(f"No RTCPeerConnection found for peer_id: {peer_id}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid peer_id"
                }))
                continue

            if msg_type == "offer":
                await self.handle_offer(pc, payload, websocket, peer_id)
            elif msg_type == "answer":
                await self.handle_answer(pc, payload, websocket, peer_id)
            elif msg_type == "ice-candidate":
                await self.handle_ice_candidate(pc, payload, websocket, peer_id)
            else:
                self.logger.warning(f"Unknown message type: {msg_type}")

    def _new_peer_id(self) -> str:
        """Return a server-owned peer ID that cannot overwrite another peer."""
        for _ in range(10):
            peer_id = f"peer_{secrets.token_urlsafe(12)}"
            if peer_id not in self.peer_connections:
                return peer_id
        raise RuntimeError("Unable to allocate a unique WebRTC peer ID")

    async def _monitor_session(
        self,
        websocket: WebSocket,
        principal: APIPrincipal,
    ) -> None:
        """Close signaling and its peer after browser-session logout or expiry."""
        if principal.kind != APIPrincipalKind.SESSION:
            await asyncio.Future()
            return
        runtime = self.api_auth_runtime
        while True:
            if runtime is None or not runtime.principal_session_is_active(principal):
                self._record_security_audit_event(
                    event_type="api.media.session",
                    outcome="denied",
                    reason="session_expired_or_revoked",
                    websocket=websocket,
                    status_code=1008,
                    principal=principal,
                    audit_policy=APIAuditPolicy.SENSITIVE_READ,
                    sensitivity=APISensitivity.MEDIA,
                )
                await websocket.close(
                    code=1008,
                    reason="Browser session expired or revoked",
                )
                return
            await asyncio.sleep(0.25)

    async def _close_peer_connection(self, peer_id: str, pc: RTCPeerConnection) -> None:
        """Close one peer connection with a bounded wait."""
        close_timeout = float(getattr(Parameters, "WEBRTC_CLOSE_TIMEOUT_SECONDS", 5.0))
        close_task = asyncio.create_task(pc.close())

        def _consume_close_result(task: asyncio.Task) -> None:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self.logger.debug("RTCPeerConnection close task failed for %s: %s", peer_id, exc)

        close_task.add_done_callback(_consume_close_result)

        try:
            await asyncio.wait_for(asyncio.shield(close_task), timeout=close_timeout)
        except asyncio.TimeoutError:
            close_task.cancel()
            self.logger.warning(
                "Timed out closing RTCPeerConnection for %s after %.1fs",
                peer_id,
                close_timeout,
            )
        except Exception as exc:
            self.logger.debug("RTCPeerConnection close ignored for %s: %s", peer_id, exc)

    async def _cleanup_peer(self, peer_id: str):
        """Close and remove a peer connection, unregister from FramePublisher."""
        pc = self.peer_connections.pop(peer_id, None)
        if pc is not None:
            try:
                await self._close_peer_connection(peer_id, pc)
            finally:
                self.frame_publisher.unregister_client()
                self.logger.info(f"Cleaned up RTCPeerConnection for {peer_id}")

    async def shutdown(self) -> int:
        """Close all active peer connections owned by this manager."""
        peer_ids = list(self.peer_connections.keys())
        if not peer_ids:
            return 0

        results = await asyncio.gather(
            *(self._cleanup_peer(peer_id) for peer_id in peer_ids),
            return_exceptions=True,
        )
        closed = 0
        for peer_id, result in zip(peer_ids, results):
            if isinstance(result, Exception):
                self.logger.warning("Error cleaning up RTCPeerConnection %s: %s", peer_id, result)
            else:
                closed += 1
        return closed

    async def handle_offer(self, pc: RTCPeerConnection, offer: Dict, websocket: WebSocket, peer_id: str):
        """Handle WebRTC offer from the client."""
        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=offer["sdp"], type=offer["type"]))
            self.logger.info(f"Set remote description for {peer_id}")

            # Add video track using FramePublisher
            video_track = VideoStreamTrackCustom(
                self.frame_publisher,
                frame_rate=getattr(Parameters, 'STREAM_FPS', 30),
            )
            pc.addTrack(video_track)
            self.logger.info(f"Added VideoStreamTrack to {peer_id}")

            # Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)

            # Send the answer back to the client
            await websocket.send_text(json.dumps({
                "type": pc.localDescription.type,
                "payload": {
                    "sdp": pc.localDescription.sdp,
                    "type": pc.localDescription.type
                },
                "peer_id": peer_id
            }))
            self.logger.info(f"Sent answer to {peer_id}")
        except Exception as e:
            self.logger.error(f"Error handling offer for {peer_id}: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to handle offer"
            }))

    async def handle_answer(self, pc: RTCPeerConnection, answer: Dict, websocket: WebSocket, peer_id: str):
        """Handle WebRTC answer from the client."""
        try:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
            self.logger.info(f"Set remote description (answer) for {peer_id}")
        except Exception as e:
            self.logger.error(f"Error handling answer for {peer_id}: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to handle answer"
            }))

    async def handle_ice_candidate(self, pc: RTCPeerConnection, candidate: Dict, websocket: WebSocket, peer_id: str):
        """Handle ICE candidate from the client."""
        try:
            if candidate:
                ice_candidate_str = candidate.get("candidate")
                sdp_mid = candidate.get("sdpMid")
                sdp_m_line_index = candidate.get("sdpMLineIndex")
                if ice_candidate_str and sdp_mid and sdp_m_line_index is not None:
                    rtc_candidate = candidate_from_sdp(ice_candidate_str)
                    rtc_candidate.sdpMid = sdp_mid
                    rtc_candidate.sdpMLineIndex = sdp_m_line_index
                    await pc.addIceCandidate(rtc_candidate)
                    self.logger.info(f"Added ICE candidate for {peer_id}")
        except Exception as e:
            self.logger.error(f"Error handling ICE candidate for {peer_id}: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Failed to handle ICE candidate"
            }))
