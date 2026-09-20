"""Optional camera controls, sharing the external provider's existing transport.

No local detector and no aircraft commands. UDP status is observational, not a
correlated target acknowledgement; motion stops are best effort, not a hardware
watchdog guarantee.
"""
from __future__ import annotations

import asyncio
import math
import struct
import threading
import time
from typing import Protocol
from urllib.parse import urlsplit

from classes.gimbal_types import TrackingState
from classes.gimbal_motion import SIP_MOTION_SETTINGS, resolve_motion


class GimbalControl(Protocol):
    capabilities: tuple[str, ...]

    async def execute(self, operation: str, *, x=None, y=None, width=None, height=None, direction=None, selection_mode=None, speed_deg_s=None, duration_ms=None) -> dict: ...

    def stop(self) -> bool: ...


def sip_frame(body: bytes) -> bytes:
    return body + f"{sum(body) & 255:02X}".encode("ascii")


def inverse_video_point(x: float, y: float, rotation: int, flip: str) -> tuple[float, float]:
    """Undo VideoHandler's rotation-then-flip using normalized image coordinates."""
    if not all(isinstance(v, (float, int)) and math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
        raise ValueError("Click coordinates must be finite and inside the video")
    if rotation not in (0, 90, 180, 270) or flip not in ("none", "horizontal", "vertical", "both"):
        raise ValueError("Unsupported video orientation")
    if flip in ("horizontal", "both"):
        x = 1 - x
    if flip in ("vertical", "both"):
        y = 1 - y
    return {0: (x, y), 90: (y, 1-x), 180: (1-x, 1-y), 270: (1-y, x)}[rotation]


def selection_region(x, y, width, height, mode):
    """Validate before any camera mutation; encode native normalized LOC fields."""
    x, y = inverse_video_point(x, y, 0, "none")
    cx, cy = round((x-.5)*2000), round((y-.5)*2000)
    if width is not None or height is not None:
        if mode != "classic":
            raise ValueError("Rectangle selection requires Classic Tracker")
        if not all(isinstance(v, (float, int)) and math.isfinite(v) and 0 < v <= 1
                   for v in (width, height)):
            raise ValueError("Rectangle width and height must be finite positive image fractions")
        if width/2 > min(x, 1-x) + 1e-12 or height/2 > min(y, 1-y) + 1e-12:
            raise ValueError("Selection rectangle must be inside the image")
        w, h, descriptor = round(width*2000), round(height*2000), 1
        if min(w, h) < 1:
            raise ValueError("Selection rectangle is too small for the camera protocol")
    else:
        w, h, descriptor = (62, 111, 9) if mode == "smart" else (67, 119, 0)
    if 2*abs(cx) + w > 2000 or 2*abs(cy) + h > 2000:
        raise ValueError("Select slightly farther from the image edge")
    return cx, cy, w, h, descriptor


class SipGimbalControl:
    """Verified SIP subset; constructed only for an explicitly enabled provider."""

    capabilities = ("set_mode", "select", "cancel", "pan", "tilt", "roll", "zoom", "home", "stop")
    STATUS_TIMEOUT = 1.5
    PULSE_SECONDS = 0.25
    motion_settings = SIP_MOTION_SETTINGS

    def __init__(self, provider):
        self.provider = provider
        self.owns_tracking = False
        self.selection_mode = "classic"
        self._command_epoch = 0

    def _send(self, body: bytes) -> None:
        # Never resurrect sockets after provider shutdown.
        with self.provider.lock:
            if not self.provider.running or not self.provider._send_command(sip_frame(body)):
                raise RuntimeError("Camera command could not be sent")

    def stop(self) -> bool:
        self._command_epoch += 1
        sent = True
        for _ in range(2):
            for body in (b"#TPPG2wPTZ00", b"#TPPM2wZMC00"):
                try:
                    self._send(body)
                except RuntimeError:
                    sent = False
        return sent

    def close(self) -> None:
        self.stop()
        if self.owns_tracking:
            for _ in range(2):
                try:
                    self._send(b"#TPPD2wTRC01")
                    self._send(b"#TPPD2wTRC00")
                except RuntimeError:
                    pass
        self.owns_tracking = False

    def _tracking_sample(self):
        with self.provider.lock:
            return self.provider.current_tracking_status, self.provider.last_tracking_update_time

    async def _command_state(self, body: bytes, expected: TrackingState) -> None:
        epoch = self._command_epoch
        sent_at = time.time()
        self._send(body)
        deadline = time.monotonic() + self.STATUS_TIMEOUT
        while time.monotonic() < deadline:
            if not self.provider.running:
                raise RuntimeError("Camera provider stopped")
            self.provider.query_tracking_status()
            await asyncio.sleep(0.08)
            if epoch != self._command_epoch:
                raise RuntimeError("Camera operation interrupted by stop")
            status, updated = self._tracking_sample()
            if status is not None and updated is not None and updated >= sent_at and status.state == expected:
                return
        raise RuntimeError(f"Camera did not report {expected.name.lower()}")

    async def _disable_tracking(self) -> None:
        status, updated = self._tracking_sample()
        if (status is None or updated is None or time.time()-updated > self.STATUS_TIMEOUT
                or status.state in (TrackingState.TRACKING_ACTIVE, TrackingState.TARGET_LOST)):
            # Vendor TRC00 exits the ready state. An active tracker must first
            # receive TRC01; otherwise this firmware can stay ready indefinitely.
            await self._command_state(b"#TPPD2wTRC01", TrackingState.TARGET_SELECTION)
        await self._command_state(b"#TPPD2wTRC00", TrackingState.DISABLED)

    async def _prepare_smart_selection(self) -> None:
        """Preserve camera detections when already ready; never run local AI."""
        status, updated = self._tracking_sample()
        if status is not None and updated is not None and 0 <= time.time()-updated <= self.STATUS_TIMEOUT:
            if status.state == TrackingState.TARGET_SELECTION:
                return
            if status.state in (TrackingState.TRACKING_ACTIVE, TrackingState.TARGET_LOST):
                await self._command_state(b"#TPPD2wTRC01", TrackingState.TARGET_SELECTION)
                return
        await self._disable_tracking()
        await self._command_state(b"#TPPD2wTRC02", TrackingState.TARGET_SELECTION)

    async def execute(self, operation: str, *, x=None, y=None, width=None, height=None, direction=None, selection_mode=None, speed_deg_s=None, duration_ms=None) -> dict:
        if operation not in self.capabilities:
            raise ValueError("Unsupported camera operation")
        if operation == "set_mode" and selection_mode not in ("classic", "smart"):
            raise ValueError("Camera selection mode must be classic or smart")
        # An invalid rectangle must not cancel an existing target or move motors.
        region = selection_region(x, y, width, height, self.selection_mode) if operation == "select" else None
        pulse_seconds = self.PULSE_SECONDS
        if operation in ("pan", "tilt", "roll"):
            speed_deg_s, duration_ms = resolve_motion(self.motion_settings, speed_deg_s, duration_ms)
            pulse_seconds = duration_ms / 1000
        elif speed_deg_s is not None or duration_ms is not None:
            raise ValueError("Movement settings are only accepted for pan, tilt and roll")
        if operation == "stop":
            sent = self.stop()
            return {"success": sent, "message": (
                "Camera movement and zoom stop commands sent." if sent else
                "Camera stop transmission failed; stopping is not confirmed.")}
        try:
            if operation == "set_mode":
                self.owns_tracking = True
                await self._disable_tracking()
                if selection_mode == "smart":
                    # TRC02 activates the camera's recognition overlay. No FED
                    # metadata decoder or local detector is needed for this path.
                    await self._command_state(b"#TPPD2wTRC02", TrackingState.TARGET_SELECTION)
                else:
                    self.owns_tracking = False
                self.selection_mode = selection_mode
                return {"success": True, "message": (
                    "Camera detection ready; click a visible detection to select it."
                    if selection_mode == "smart" else "Classic camera selection ready.")}
            if operation == "select":
                self.owns_tracking = True
                if self.selection_mode == "smart":
                    await self._prepare_smart_selection()
                else:
                    # Manual click or Qt rectangle (descriptor 1), fuzzy off.
                    # Establish an inactive barrier even when replacing a target.
                    await self._disable_tracking()
                    await self._command_state(b"#TPPD2wTRC02", TrackingState.TARGET_SELECTION)
                self._send(b"#tpPDAwLOC" + struct.pack(">hhhhH", *region))
                return {"success": True, "message": "Target coordinates sent; waiting for camera tracking status."}
            if operation == "cancel":
                self.owns_tracking = True
                await self._disable_tracking()
                self.owns_tracking = False
                self.stop()
                return {"success": True, "message": "Camera reports tracking disabled."}
            if operation in ("pan", "tilt", "roll", "zoom") and direction not in (-1, 1):
                raise ValueError("Movement direction must be -1 or 1")
            # Camera movement overrides its tracker only after disabled is observed.
            await self._disable_tracking()
            self.owns_tracking = False
            if operation == "home":
                self._send(b"#TPPG2wPTZ05")
                return {"success": True, "message": "Camera home command sent."}
            if operation == "zoom":
                body = b"#TPPM2wZMC02" if direction == 1 else b"#TPPM2wZMC01"
            else:
                axis = {"pan": "GSY", "tilt": "GSP", "roll": "GSR"}[operation]
                source = "P" if operation == "roll" else "U"
                body = f"#TP{source}G2w{axis}{(speed_deg_s*direction)&255:02X}".encode("ascii")
            # Independent best-effort deadline if the async loop stalls. It does
            # not cover process death, network loss or device-side watchdogs.
            timer = threading.Timer(pulse_seconds + 0.15, self.stop)
            timer.daemon = True
            timer.start()
            try:
                self._send(body)
                await asyncio.sleep(pulse_seconds)
            finally:
                self.stop()
                timer.cancel()
            result = {"success": True, "message": "Bounded camera movement command sent."}
            if operation in ("pan", "tilt", "roll"):
                result.update(speed_deg_s=speed_deg_s, duration_ms=duration_ms)
            return result
        except BaseException:
            self.close()
            raise


def _provider(app):
    tracker = getattr(app, "tracker", None)
    if not getattr(tracker, "is_external_tracker", False):
        return None
    return getattr(tracker, "gimbal_provider", None)


def get_gimbal_control_status(app) -> dict:
    provider = _provider(app)
    control = getattr(provider, "manual_control", None)
    enabled = control is not None
    data = provider.get_current_data() if enabled else None
    state = data.tracking_status.state if data and data.tracking_status else None
    connected = bool(enabled and provider.running and data and data.angles and state is not None)
    following = bool(getattr(app, "following_active", False))
    reason = ("disabled" if not enabled else
              "application_shutting_down" if getattr(app, "shutdown_flag", False) else
              "camera_unavailable" if not connected else
              "tracking_unsupported" if state == TrackingState.UNSUPPORTED else
              "stop_following_first" if following else None)
    return dict(enabled=enabled, available=reason is None, connected=connected,
                selection_mode=getattr(control, "selection_mode", "classic"),
                tracking_state=state.name.lower() if state is not None else "unknown",
                following_active=following, capabilities=list(control.capabilities) if enabled else [],
                motion_settings=getattr(control, "motion_settings", None) if enabled else None,
                reason=reason)


def _camera_point(app, provider, x, y):
    video = getattr(app, "video_handler", None)
    source = getattr(video, "selection_source", {})
    if (source.get("type") not in ("RTSP_OPENCV", "RTSP_STREAM") or
            urlsplit(source.get("url", "")).hostname != provider.gimbal_ip):
        raise ValueError("Manual camera selection requires this gimbal's RTSP video")
    frame = video.get_frame_status()
    stamp = frame.get("last_successful_frame_time")
    if (frame.get("source") != "fresh" or not isinstance(stamp, (int, float)) or
            not 0 <= time.time()-stamp <= 2):
        raise ValueError("A fresh camera video frame is required")
    return inverse_video_point(x, y, video._frame_rotation_deg, video._frame_flip_mode)


async def execute_gimbal_control(app, request) -> dict:
    """Run on the existing owner loop under its tracker/follower lifecycle barrier."""
    async def execute():
        # Stop must preempt a pending handshake/pulse, not queue behind its
        # lifecycle lock and allow a new movement to start after Stop was clicked.
        if request.operation == "stop":
            provider = _provider(app)
            control = getattr(provider, "manual_control", None)
            if control is not None:
                return await control.execute("stop")
        lock = getattr(app, "_follower_state_lock", None)
        if lock is None:
            return {"success": False, "reason": "lifecycle_unavailable", "message": "Control lifecycle unavailable."}
        async with lock:
            status = get_gimbal_control_status(app)
            operation = request.operation
            abort_allowed = status["enabled"] and (
                operation == "stop" or operation == "cancel" and not status["following_active"])
            if not status["available"] and not abort_allowed:
                return {"success": False, "reason": status["reason"], "message": "Camera control unavailable: " + str(status["reason"])}
            provider = _provider(app)
            try:
                x, y = request.x, request.y
                width, height = request.width, request.height
                if operation == "select":
                    x, y = _camera_point(app, provider, x, y)
                    if app.video_handler._frame_rotation_deg in (90, 270):
                        width, height = height, width
                if operation != "stop":
                    # Following cannot start while the operation holds this lock.
                    app._advance_tracking_session_generation()
                if operation == "set_mode":
                    return await provider.manual_control.execute(operation, selection_mode=request.selection_mode)
                motion = {}
                if request.speed_deg_s is not None or request.duration_ms is not None:
                    resolve_motion(getattr(provider.manual_control, "motion_settings", None),
                                   request.speed_deg_s, request.duration_ms)
                    motion = dict(speed_deg_s=request.speed_deg_s, duration_ms=request.duration_ms)
                return await provider.manual_control.execute(operation, x=x, y=y, width=width, height=height, direction=request.direction, **motion)
            except (RuntimeError, ValueError) as exc:
                reason = ("camera_control_interrupted" if str(exc) == "Camera operation interrupted by stop"
                          else "camera_control_failed")
                return {"success": False, "reason": reason, "message": str(exc)}
    return await app._run_on_flight_event_loop(execute)
