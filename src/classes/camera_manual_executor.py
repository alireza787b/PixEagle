"""Latest-intent camera control on a loop independent of capture and inference."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from contextlib import contextmanager


class CameraManualExecutor:
    RENEW_INTERVAL_MS = 100
    LEASE_TIMEOUT_MS = 350
    CHECK_SECONDS = 0.02

    def __init__(self, runtime, control):
        self.runtime = runtime
        self.control = control
        self._actor = None
        self._guard = None
        self._intent = None
        self._deadline = 0.0
        self._prepared = False
        self._serial = 0
        self._dispatched = None
        self._closed = False
        self._loop = None
        self._preparation = None
        self._retired = deque(maxlen=256)
        self._state = dict(gesture_id=None, sequence=-1, state="idle", reason=None,
                          renew_interval_ms=self.RENEW_INTERVAL_MS, lease_timeout_ms=self.LEASE_TIMEOUT_MS,
                          accepted_at_monotonic=None, dispatched_at_monotonic=None, stopped_at_monotonic=None)
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="camera-manual", daemon=True)
        self._thread.start()
        if not self._ready.wait(1):
            raise RuntimeError("Camera manual executor could not start")

    @property
    def active(self):
        return self._state["state"] in {"preparing", "moving", "idle"} and self._state["gesture_id"] is not None

    def snapshot(self):
        with self.runtime._lock:
            return dict(self._state)

    def submit(self, actor, operation, gesture_id, sequence, intent, guard, received_at=None):
        with self.runtime._lock:
            now = time.monotonic()
            received_at = now if received_at is None else received_at
            if now - received_at >= self.LEASE_TIMEOUT_MS / 1000:
                raise ValueError("Camera input expired before admission")
            if intent["axis"] not in self.control.capabilities:
                raise ValueError("Camera does not support this manual axis")
            if self._closed:
                raise ValueError("Camera owner is closed")
            if self.active and now >= self._deadline:
                self._stop_locked("lease_expired", state="expired")
            self.runtime.validate_guard(guard)
            if (actor, gesture_id) in self._retired:
                raise ValueError("Camera gesture already ended; start a new gesture")
            if self._state["reason"] == "stop_transmission_failed":
                raise ValueError("Retry camera Stop before starting another gesture")
            if operation == "manual_begin":
                if (self.active or self.runtime._busy or self.runtime._lifecycle_users
                        or now < self.runtime._lease_until and actor != self.runtime._actor):
                    raise ValueError("Another camera command or lifecycle operation is active")
                if getattr(self.runtime.app, "following_active", False):
                    raise ValueError("Stop following before moving the camera")
                self._serial += 1
                self._actor, self._guard = actor, dict(guard)
                self._prepared, self._dispatched = False, None
                self._state.update(gesture_id=gesture_id, sequence=sequence, state="preparing", reason=None,
                                   dispatched_at_monotonic=None, stopped_at_monotonic=None)
            elif not self.active or actor != self._actor or gesture_id != self._state["gesture_id"]:
                raise ValueError("Camera gesture is not active")
            elif sequence <= self._state["sequence"]:
                raise ValueError("Camera input sequence is stale")
            self._state.update(sequence=sequence, accepted_at_monotonic=received_at)
            self._intent = dict(intent)
            self._deadline = received_at + self.LEASE_TIMEOUT_MS / 1000
            return self.snapshot()

    def stop(self, actor=None, gesture_id=None, *, reason="operator_stop"):
        with self.runtime._lock:
            if gesture_id is not None:
                retired = (actor, gesture_id) in self._retired
                self._retired.append((actor, gesture_id))
                matches = actor == self._actor and gesture_id == self._state["gesture_id"]
                if self.active and not matches:
                    return True, dict(self._state)
                if not self.active:
                    if matches and self._state["reason"] == "stop_transmission_failed":
                        return self._stop_locked(reason), self.snapshot()
                    if not retired and not self.runtime._busy:
                        # A Stop before begin retires its captured generation too.
                        self.runtime._generation += 1
                    return True, dict(self._state)
            return self._stop_locked(reason), self.snapshot()

    def _stop_locked(self, reason, *, state="stopped"):
        if self._state["gesture_id"] is not None:
            self._retired.append((self._actor, self._state["gesture_id"]))
        self._serial += 1
        self._deadline = 0.0
        self._intent = None
        self._prepared = False
        self.runtime._generation += 1
        self.runtime._lease_until = 0.0
        self.runtime._motion = False
        try:
            sent = self.control.stop()
        except Exception:
            sent = False
            logging.getLogger(__name__).exception("Camera Stop transmission raised")
        self._state.update(state=state if sent else "failed", reason=reason if sent else "stop_transmission_failed",
                           stopped_at_monotonic=time.monotonic())
        self._dispatched = None
        task = self._preparation
        if task is not None and not task.done() and self._loop is not None:
            self._loop.call_soon_threadsafe(task.cancel)
        logging.getLogger(__name__).info("Camera manual ended gesture=%s sequence=%s reason=%s stop_sent=%s",
            self._state["gesture_id"], self._state["sequence"], reason, sent)
        return sent

    async def _prepare(self, gesture_id, serial):
        try:
            @contextmanager
            def command_guard():
                with self.runtime._lock:
                    if (not self.active or self._serial != serial
                            or time.monotonic() >= self._deadline):
                        raise RuntimeError("Camera gesture ended before preparation command")
                    self.runtime.validate_guard(self._guard)
                    yield
            await self.control.prepare_manual(command_guard)
            with self.runtime._lock:
                if self.active and self._serial == serial and time.monotonic() < self._deadline:
                    self._prepared = True
        except asyncio.CancelledError:
            pass
        except Exception:
            logging.getLogger(__name__).exception("Camera manual preparation failed gesture=%s", gesture_id)
            with self.runtime._lock:
                if self.active and self._serial == serial:
                    self._stop_locked("camera_preparation_failed", state="failed")

    async def _watch(self):
        while True:
            with self.runtime._lock:
                if self._closed:
                    return
                if self.active:
                    try:
                        self.runtime.validate_guard(self._guard)
                        data = self.runtime.provider.get_current_data()
                        if (not self.runtime.provider.running or data is None or data.angles is None
                                or data.tracking_status is None or getattr(self.runtime.app, "following_active", False)
                                or getattr(self.runtime.app, "shutdown_flag", False)):
                            self._stop_locked("camera_unavailable", state="failed")
                        elif time.monotonic() >= self._deadline:
                            self._stop_locked("lease_expired", state="expired")
                        elif not self._prepared:
                            if self._preparation is None or self._preparation.done():
                                self._preparation = asyncio.create_task(self._prepare(self._state["gesture_id"], self._serial))
                        elif self._state["sequence"] > 0 and self._intent != self._dispatched:
                            # Guard, expiry and Stop are serialized with the final device write.
                            self.control.send_manual_intent(**self._intent)
                            logging.getLogger(__name__).info(
                                "Camera manual dispatch gesture=%s sequence=%s input_age_ms=%.1f axis=%s value=%.3f",
                                self._state["gesture_id"], self._state["sequence"],
                                (time.monotonic() - self._state["accepted_at_monotonic"]) * 1000,
                                self._intent["axis"], self._intent["value"])
                            self._dispatched = dict(self._intent)
                            self._state.update(state="moving" if self._intent["value"] else "idle",
                                               dispatched_at_monotonic=time.monotonic())
                    except Exception:
                        logging.getLogger(__name__).exception("Camera manual dispatch failed")
                        self._stop_locked("camera_control_failed", state="failed")
            await asyncio.sleep(self.CHECK_SECONDS)

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_until_complete(self._watch())
        finally:
            for task in asyncio.all_tasks(loop):
                task.cancel()
            loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True))
            loop.close()
            asyncio.set_event_loop(None)

    def close(self):
        with self.runtime._lock:
            if self._closed:
                return
            self._stop_locked("camera_closed")
            self._closed = True
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=1)
