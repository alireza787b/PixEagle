"""One application-owned camera transport, independent of the selected tracker."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager, nullcontext

from classes.gimbal_provider import GimbalInputProvider, create_gimbal_provider
from classes.gimbal_types import CameraObservationSource


class CameraLifecycleBusy(ValueError):
    """A camera control owner excludes a conflicting lifecycle transition."""


class CameraRuntime:
    """Own transport lifetime and reject interleaved control clients."""

    LEASE_SECONDS = 2.0
    MAX_HOLD_SECONDS = 10.0

    def __init__(self, app, settings):
        self.app = app
        self.settings = dict(settings)
        self._provider = None
        self.camera_id = str(uuid.uuid4())
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._actor = None
        self._lease_until = 0.0
        self._hold_started = 0.0
        self._busy = False
        self._busy_operation = None
        self._admitted_at = 0.0
        self._motion = False
        self._closed = False
        self._generation = 0
        self._initial_source_epoch = None
        self._manual = None
        self._lifecycle_users = 0
        self._observation_available = False
        self._source_generation = 0
        self._bound_provider = None
        self._observation_since = time.monotonic()
        self._observation_min_sequence = 0

    @property
    def provider(self):
        return self._provider

    @provider.setter
    def provider(self, value):
        with self._lock:
            if self._bound_provider is not None and value is not self._bound_provider:
                raise ValueError('camera_provider_replacement_requires_new_owner')
            self._provider = value

    def get_provider(self):
        with self._lock:
            if self._closed or self.settings.get("ENABLED") is not True:
                raise ValueError("Camera provider is disabled")
            if self.provider is None:
                self.provider = create_gimbal_provider(self.settings)
            if self.provider is not self._bound_provider:
                if isinstance(self.provider, GimbalInputProvider):
                    provider = self.provider
                    provider.set_lifecycle_observer(lambda event, token: self._provider_lifecycle(provider, event, token))
                self._bound_provider = self.provider
            return self.provider

    def start(self):
        with self._start_lock:
            with self._lock:
                provider = self.get_provider()
                restarting = not provider.running
                observed_lifecycle = isinstance(provider, GimbalInputProvider)
                if restarting and not observed_lifecycle:
                    self._retire_observation_source()
            started = bool(provider.start_listening()) if restarting else True
            with self._lock:
                current = not self._closed and provider is self.provider
                if observed_lifecycle:
                    current = current and self._observation_available
                control = getattr(provider, 'manual_control', None)
                prepare_manual = (started and current and callable(getattr(control, 'prepare_manual', None))
                                  and callable(getattr(control, 'send_manual_intent', None)) and self._manual is None)
                source_generation = self._source_generation
            if prepare_manual:
                from classes.camera_manual_executor import CameraManualExecutor
                candidate = CameraManualExecutor(self, control)
                with self._lock:
                    attach = (not self._closed and provider is self.provider and self._manual is None
                              and control is getattr(provider, 'manual_control', None)
                              and source_generation == self._source_generation)
                    if attach:
                        self._manual = candidate
                if not attach:
                    candidate.close()
            with self._lock:
                current = not self._closed and provider is self.provider and source_generation == self._source_generation
                if observed_lifecycle:
                    current = current and self._observation_available
                discard_transport = self._closed or source_generation == self._source_generation
            if started and not current and restarting and discard_transport:
                provider.stop_listening()
            return started and current

    def _retire_observation_source(self):
        self._source_generation += 1
        self._generation += 1
        self._observation_available = False
        self._observation_since = time.monotonic()
        sequence = getattr(self.provider, 'angle_sample_sequence', 0)
        self._observation_min_sequence = sequence if type(sequence) is int else 0

    def _provider_lifecycle(self, provider, event, token):
        with self._lock:
            if provider is not self.provider or provider is not self._bound_provider:
                return None if event == 'starting' else False
            if event == 'starting':
                if self._closed:
                    return None
                self._retire_observation_source()
                return self._source_generation
            if event == 'stopping':
                self._retire_observation_source()
            elif event == 'started':
                current = not self._closed and token == self._source_generation
                self._observation_available = current
                return current
            elif event == 'failed' and token == self._source_generation:
                self._observation_available = False
            return False

    def angle_source_identity(self) -> CameraObservationSource | None:
        with self._lock:
            if not isinstance(self.provider, GimbalInputProvider) or self.provider is not self._bound_provider:
                return None
            return CameraObservationSource(self.camera_id, self._source_generation)

    def angle_observation_context(self) -> CameraObservationSource | None:
        with self._lock:
            if self._closed or not self._observation_available or self.provider is None or not self.provider.running:
                return None
            return self.angle_source_identity()

    def angle_receipt_matches_source(self, source, sequence, received) -> bool:
        with self._lock:
            return (type(sequence) is int and sequence > self._observation_min_sequence
                    and self._receipt_matches_source(source, received))

    def tracking_receipt_matches_source(self, source, received) -> bool:
        with self._lock:
            return self._receipt_matches_source(source, received)

    def _receipt_matches_source(self, source, received):
        return (source is not None and source == self.angle_observation_context()
                and isinstance(received, (int, float)) and not isinstance(received, bool)
                and self._observation_since < received <= time.monotonic())

    def guard(self):
        publisher = getattr(self.app, "frame_publisher", None)
        source = (publisher.control_source_epoch if hasattr(publisher, "control_source_epoch")
                  else publisher.video_context().get("source_epoch") if publisher else None)
        with self._lock:
            if self._initial_source_epoch is None and source is not None:
                self._initial_source_epoch = source
        revision = f"{getattr(self.app, 'current_tracker_type', 'unknown')}:{bool(getattr(self.app, 'smart_mode_active', False))}"
        return dict(camera_id=self.camera_id, camera_generation=f"{self._generation}:{revision}", source_epoch=source)

    @property
    def busy(self):
        with self._lock:
            return self._busy or bool(self._manual and self._manual.active)

    @property
    def motion_active(self):
        with self._lock:
            return bool(self._manual and self._manual.active) or (self._motion and (self._busy or time.monotonic() < self._lease_until))

    def validate_guard(self, guard, *, stop=False):
        current = self.guard()
        if guard.get("camera_id") != current["camera_id"]:
            raise ValueError("Camera owner changed. Refresh camera state.")
        # A context captured before the first frame has no source epoch. The
        # first authenticated source attachment fills that unknown value; a
        # later source replacement remains a stale-command conflict.
        source_is_initializing = (guard.get("source_epoch") is None
                                  and current.get("source_epoch") is not None
                                  and current["source_epoch"] == self._initial_source_epoch)
        comparable_guard = dict(guard)
        if source_is_initializing:
            comparable_guard["source_epoch"] = current["source_epoch"]
        if not stop and comparable_guard != current:
            raise ValueError("Camera, source or target changed. Refresh camera state.")

    def acquire(self, actor, operation):
        with self._lock:
            now = time.monotonic()
            if self._closed:
                raise ValueError("Camera owner is closed")
            if operation == "stop":
                self._generation += 1
                self._lease_until = 0.0
                self._motion = False
                return
            if self._manual and self._manual.snapshot()["reason"] == "stop_transmission_failed":
                raise CameraLifecycleBusy("Retry camera Stop before starting another operation")
            if (self._manual and self._manual.active) or self._busy or self._lifecycle_users or (now < self._lease_until and actor != self._actor):
                raise ValueError("Another camera command or control hold is active")
            motion = operation in {"pan", "tilt", "roll", "zoom"}
            if motion and actor == self._actor and now < self._lease_until:
                if now - self._hold_started >= self.MAX_HOLD_SECONDS:
                    raise ValueError("Camera hold limit reached. Release the control before continuing.")
            else:
                self._hold_started = now
            self._actor = actor
            self._busy = True
            self._busy_operation = operation
            self._admitted_at = now
            self._motion = motion
            self._lease_until = now + self.LEASE_SECONDS if motion else 0.0

    def release(self, *, failed=False):
        with self._lock:
            self._busy = False
            self._busy_operation = None
            if failed or not self._motion:
                self._lease_until = 0.0
                self._motion = False

    def detach_tracker(self):
        """Cancel only adapter-owned tracking; retain the shared transport."""
        with self._lock:
            if self._manual and self._manual.active:
                self._manual.stop(reason="tracker_changed")
            self._generation += 1
            control = getattr(self.provider, "manual_control", None)
            if control is not None:
                control.close()
            self._lease_until = 0.0
            self._motion = False

    def close(self):
        with self._lock:
            self._closed = True
            self._retire_observation_source()
            self._observation_available = False
            provider, manual = self.provider, self._manual
            self._motion = False
            self._lease_until = 0.0
        if manual is not None:
            manual.close()
        if provider is not None:
            provider.stop_listening()

    @contextmanager
    def lifecycle_reservation(self, *, cancel_manual=False):
        with self._lock:
            if self._manual and self._manual.snapshot()["reason"] == "stop_transmission_failed":
                raise CameraLifecycleBusy("Retry camera Stop before changing the camera lifecycle")
            if self._busy and (not cancel_manual or self._busy_operation in {"pan", "tilt", "roll", "zoom", "home"}):
                raise CameraLifecycleBusy("A camera command is active")
            if self._manual and self._manual.active:
                if not cancel_manual:
                    raise CameraLifecycleBusy("Release camera controls before starting this operation")
                sent, _ = self._manual.stop(reason="lifecycle_changed")
                if not sent:
                    raise CameraLifecycleBusy("Camera Stop failed; retry Stop before changing the lifecycle")
            self._lifecycle_users += 1
        try:
            yield
        finally:
            with self._lock:
                self._lifecycle_users -= 1

    @property
    def manual_supported(self):
        return self._manual is not None

    def manual_snapshot(self):
        return self._manual.snapshot() if self._manual is not None else None

    def manual_action(self, actor, request, *, received_at=None):
        if self._manual is None:
            raise ValueError("Continuous manual control is unavailable")
        self.validate_guard(request.camera_context.guard.model_dump(), stop=request.operation == "stop")
        if request.operation == "stop":
            sent, state = self._manual.stop(actor, request.gesture_id)
            return dict(success=sent, reason=state.get("reason"), manual=state,
                        message="Camera stop sent." if sent else "Camera stop transmission failed.")
        state = self._manual.submit(actor, request.operation, request.gesture_id, request.sequence,
                                    request.intent.model_dump(), request.camera_context.guard.model_dump(), received_at)
        return dict(success=True, reason="manual_intent_accepted", manual=state,
                    message="Camera manual intent accepted; device motion is not acknowledged.")

    async def execute_discrete(self, request):
        """Compatibility finite commands share the independent camera executor."""
        if request.operation == "stop":
            sent, state = self._manual.stop()
            return dict(success=sent, reason=state["reason"], message="Camera Stop sent." if sent else "Camera Stop failed.")
        guard = request.camera_context.guard.model_dump() if request.camera_context else self.guard()
        admitted = self._admitted_at if self._busy else time.monotonic()
        @contextmanager
        def command_guard():
            with self._lock:
                self.validate_guard(guard)
                data = self.provider.get_current_data()
                if not self.provider.running or data is None or data.angles is None or data.tracking_status is None:
                    raise RuntimeError("Camera telemetry is unavailable")
                if time.monotonic() - admitted >= 0.35:
                    raise RuntimeError("Camera command expired before dispatch")
                if getattr(self.app, "following_active", False) or self._lifecycle_users:
                    raise RuntimeError("Camera lifecycle changed before dispatch")
                yield
        async def run():
            try:
                with command_guard():
                    pass
                return await self.provider.manual_control.execute(request.operation, direction=request.direction,
                    speed_deg_s=request.speed_deg_s, duration_ms=request.duration_ms, selection_guard=command_guard)
            except (RuntimeError, ValueError) as exc:
                return dict(success=False, reason=("camera_control_interrupted" if guard != self.guard()
                    or str(exc) == "Camera operation interrupted by stop" else "camera_control_failed"), message=str(exc))
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(run(), self._manual._loop))


@asynccontextmanager
async def camera_lifecycle(app, *, cancel_manual=False):
    runtime = getattr(app, "camera_runtime", None)
    with runtime.lifecycle_reservation(cancel_manual=cancel_manual) if runtime is not None else nullcontext():
        yield
