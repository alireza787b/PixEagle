"""Bounded per-client JPEG policies driven by measured delivery feedback.

Encoded byte rate describes offered/delivered traffic, never link capacity.
Legacy callers without delivery feedback retain their requested quality.
"""

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class _Profile:
    quality_floor: int
    quality_ceiling: int
    fps_ceiling: float
    scales: tuple[float, ...]


@dataclass
class ClientQualityState:
    client_id: str
    current_quality: int
    profile: str
    limits: _Profile
    fps: float
    can_resize: bool = True
    resolution_index: int = 0
    bandwidth_ewma: float = 0.0
    encoding_time_ewma: Optional[float] = None
    send_time_ewma: Optional[float] = None
    ack_time_ewma: Optional[float] = None
    presentation_time_ewma: Optional[float] = None
    last_delivery_at: Optional[float] = None
    last_policy_sample_at: Optional[float] = None
    last_adjustment_time: float = 0.0
    pressure_samples: int = 0
    healthy_samples: int = 0
    quality_direction: int = 0
    adjustment_reason: str = "awaiting_feedback"
    total_frames: int = 0
    total_bytes: int = 0


class AdaptiveQualityEngine:
    """Recommend quality, FPS and resolution; transports apply the policy.

    ACK duration measures delivery, including the peer's ACK policy. It must
    not be reported as presentation latency. CPU load remains diagnostic:
    unrelated tracking work or another slow client cannot reduce this policy.
    """

    PROFILES = ("automatic", "high_quality", "low_bandwidth")

    def __init__(self, *, clock: Optional[Callable[[], float]] = None):
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._clients: Dict[str, ClientQualityState] = {}
        self._cpu_load = 0.0
        self._cpu_available = False
        self._load_config()

    def _load_config(self) -> None:
        from classes.parameters import Parameters

        self.min_quality = max(1, min(100, int(getattr(Parameters, "MIN_QUALITY", 30))))
        self.max_quality = max(self.min_quality, min(100, int(getattr(Parameters, "MAX_QUALITY", 85))))
        self.default_quality = max(self.min_quality, min(self.max_quality, int(getattr(Parameters, "STREAM_QUALITY", 50))))
        self.default_profile = getattr(Parameters, "STREAM_PROFILE", "automatic")
        if self.default_profile not in self.PROFILES:
            self.default_profile = "automatic"
        self.stream_fps = max(1.0, min(60.0, float(getattr(Parameters, "STREAM_FPS", 20))))
        self.startup_fps = max(1.0, min(self.stream_fps, float(getattr(Parameters, "STREAM_STARTUP_FPS", 12))))
        self.startup_scale = max(0.25, min(1.0, float(getattr(Parameters, "STREAM_STARTUP_SCALE", 0.75))))
        self.quality_step = max(1, int(getattr(Parameters, "QUALITY_STEP_ADAPTIVE", 5)))
        self.bandwidth_alpha = max(0.0, min(1.0, float(getattr(Parameters, "BANDWIDTH_EWMA_ALPHA", 0.3))))
        self.encoding_alpha = max(0.0, min(1.0, float(getattr(Parameters, "ENCODING_EWMA_ALPHA", 0.2))))
        self.cooldown_seconds = max(0.0, float(getattr(Parameters, "QUALITY_COOLDOWN_SECONDS", 2.0)))
        self.encoding_threshold = max(0.001, float(getattr(Parameters, "ENCODING_TIME_THRESHOLD_MS", 20)) / 1000)

    def _limits(self, profile: str) -> _Profile:
        if profile not in self.PROFILES:
            raise ValueError("Unknown streaming profile")
        floor = {"automatic": 55, "high_quality": 70, "low_bandwidth": 45}[profile]
        # Automatic keeps existing configured quality values valid.
        if profile != "high_quality":
            floor = min(floor, self.default_quality)
        floor = max(self.min_quality, min(self.max_quality, floor))
        ceiling = self.max_quality if profile != "low_bandwidth" else max(floor, min(self.max_quality, 65))
        fps = self.stream_fps if profile != "low_bandwidth" else min(self.stream_fps, 10.0)
        scales = {"automatic": (1.0, 0.75, 0.5, 0.25), "high_quality": (1.0, 0.75), "low_bandwidth": (0.75, 0.5, 0.25)}[profile]
        return _Profile(floor, ceiling, fps, scales)

    def register_client(
        self, client_id: str, initial_quality: Optional[int] = None, *,
        profile: Optional[str] = None, can_resize: bool = True,
    ) -> None:
        profile = profile or self.default_profile
        limits = self._limits(profile)
        quality = self.default_quality if initial_quality is None else initial_quality
        with self._lock:
            startup_index = (min(range(len(limits.scales)), key=lambda index: abs(limits.scales[index] - self.startup_scale))
                             if profile == "automatic" else 0)
            startup_fps = self.startup_fps if profile == "automatic" else limits.fps_ceiling
            self._clients[client_id] = ClientQualityState(
                client_id=client_id,
                current_quality=max(limits.quality_floor, min(limits.quality_ceiling, quality)),
                profile=profile,
                limits=limits,
                fps=startup_fps,
                can_resize=can_resize,
                resolution_index=startup_index,
                last_adjustment_time=self._clock(),
            )

    def unregister_client(self, client_id: str) -> None:
        with self._lock:
            self._clients.pop(client_id, None)

    def set_client_profile(self, client_id: str, profile: str) -> None:
        limits = self._limits(profile)
        with self._lock:
            state = self._clients.get(client_id)
            if state is None:
                return
            state.profile = profile
            state.limits = limits
            state.current_quality = max(limits.quality_floor, min(limits.quality_ceiling, self.default_quality))
            state.fps = limits.fps_ceiling
            state.resolution_index = 0
            self._reset_feedback(state)
            state.last_adjustment_time = self._clock()
            state.adjustment_reason = "profile_changed"

    @staticmethod
    def _valid_nonnegative(value) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

    @staticmethod
    def _smooth(previous: Optional[float], sample: float, alpha: float) -> float:
        return sample if previous is None else alpha * sample + (1 - alpha) * previous

    @staticmethod
    def _reset_feedback(state: ClientQualityState) -> None:
        state.send_time_ewma = None
        state.ack_time_ewma = None
        state.encoding_time_ewma = None
        state.presentation_time_ewma = None
        state.last_delivery_at = None
        state.last_policy_sample_at = None
        state.bandwidth_ewma = 0.0
        state.pressure_samples = state.healthy_samples = 0
        state.quality_direction = 0

    def report_frame_sent(self, client_id: str, frame_size_bytes: int, encoding_time_seconds: float) -> int:
        """Compatibility diagnostics only: encoding elapsed may include queue wait.

        New transports call report_delivery instead, once per completed frame.
        No congestion or recovery is inferred from these legacy arguments.
        """
        with self._lock:
            state = self._clients.get(client_id)
            if state is None:
                return self.default_quality
            if (self._valid_nonnegative(frame_size_bytes)
                    and self._valid_nonnegative(encoding_time_seconds)):
                state.total_frames += 1
                state.total_bytes += frame_size_bytes
                state.encoding_time_ewma = self._smooth(state.encoding_time_ewma, encoding_time_seconds, self.encoding_alpha)
            return state.current_quality

    def report_delivery(
        self, client_id: str, frame_size_bytes: int, *, send_time_seconds: float,
        ack_time_seconds: Optional[float] = None,
        encoding_time_seconds: Optional[float] = None,
        presentation_delay_seconds: Optional[float] = None,
        dropped_frames: int = 0,
        can_resize: bool = True,
    ) -> Optional[dict]:
        """Report one completed delivery using local monotonic durations.

        Call at matched ACK receipt when negotiated, otherwise after the write.
        ACK time runs from send start; encoding time excludes executor wait and
        cache hits. Presentation delay is optional measured receiver feedback,
        never a subtraction between unsynchronized host clocks. Dropped frames
        is the receiver's delta for this sample, not its lifetime counter.
        Invalid feedback is ignored atomically. Expired/unmatched deliveries
        must be rejected by the transport before calling this method.
        """
        values = (frame_size_bytes, send_time_seconds, dropped_frames)
        optional = (ack_time_seconds, encoding_time_seconds, presentation_delay_seconds)
        valid = (all(self._valid_nonnegative(value) for value in values)
                 and all(value is None or self._valid_nonnegative(value) for value in optional)
                 and isinstance(frame_size_bytes, int) and isinstance(dropped_frames, int)
                 and isinstance(can_resize, bool)
                 and (ack_time_seconds is None or ack_time_seconds >= send_time_seconds))
        now = self._clock()
        with self._lock:
            state = self._clients.get(client_id)
            if state is None:
                return None
            if not valid or (state.last_delivery_at is not None and now <= state.last_delivery_at):
                return self._policy(state)
            state.can_resize = can_resize
            previous = state.last_delivery_at
            if previous is not None and now - previous > max(5.0, self.cooldown_seconds * 3):
                self._reset_feedback(state)
                previous = None
            if previous is not None:
                measured_rate = frame_size_bytes / (now - previous)
                state.bandwidth_ewma = self._smooth(state.bandwidth_ewma or None, measured_rate, self.bandwidth_alpha)
            state.last_delivery_at = now
            state.total_frames += 1
            state.total_bytes += frame_size_bytes
            state.send_time_ewma = self._smooth(state.send_time_ewma, send_time_seconds, self.bandwidth_alpha)
            for attribute, sample in (("ack_time_ewma", ack_time_seconds),
                                      ("encoding_time_ewma", encoding_time_seconds),
                                      ("presentation_time_ewma", presentation_delay_seconds)):
                setattr(state, attribute, None if sample is None else self._smooth(getattr(state, attribute), sample, self.encoding_alpha))
            self._adjust(
                state, now, dropped_frames,
                send_time_seconds, ack_time_seconds,
                encoding_time_seconds, presentation_delay_seconds,
                can_resize=can_resize,
            )
            return self._policy(state)

    def report_budget_pressure(
        self, client_id: str, *, oversized: bool = False, can_resize: bool = True,
    ) -> Optional[dict]:
        """Record rejected shared-budget work without inventing a delivery."""
        with self._lock:
            state = self._clients.get(client_id)
            if state is None:
                return None
            state.can_resize = can_resize
            if oversized:
                # Cadence cannot make one JPEG fit the serialization horizon.
                previous_quality = state.current_quality
                state.adjustment_reason = "frame_exceeds_budget"
                if can_resize and state.resolution_index < len(state.limits.scales) - 1:
                    state.resolution_index += 1
                elif state.current_quality > state.limits.quality_floor:
                    state.current_quality = max(state.limits.quality_floor,
                                                state.current_quality - self.quality_step)
                else:
                    state.adjustment_reason = "unavailable_at_configured_limits"
                state.quality_direction = -1 if state.current_quality < previous_quality else 0
                state.last_adjustment_time = state.last_policy_sample_at = self._clock()
                state.pressure_samples = state.healthy_samples = 0
                return self._policy(state)
            self._adjust(
                state, self._clock(), 0, 0.0, None, None, None,
                forced_pressure="shared_budget", can_resize=can_resize,
            )
            return self._policy(state)

    def _adjust(
        self, state: ClientQualityState, now: float, dropped_frames: int,
        send_time: float, ack_time: Optional[float],
        encoding_time: Optional[float], presentation_time: Optional[float],
        *, forced_pressure: Optional[str] = None, can_resize: bool = True,
    ) -> None:
        if (state.last_policy_sample_at is not None
                and now - state.last_policy_sample_at > max(5.0, self.cooldown_seconds * 3)):
            state.pressure_samples = state.healthy_samples = 0
        state.last_policy_sample_at = now
        interval = 1.0 / state.fps
        pressure = forced_pressure
        # Count actual bad deliveries, not the decaying tail of one EWMA spike.
        if dropped_frames or (presentation_time is not None and presentation_time > max(0.15, interval * 2)):
            pressure = "presentation_pressure"
        elif send_time > interval * 0.8:
            pressure = "send_delay"
        elif ack_time is not None and ack_time > max(0.15, interval * 1.5):
            pressure = "delivery_delay"
        elif encoding_time is not None and encoding_time > max(self.encoding_threshold, interval * 0.6):
            pressure = "encoding_pressure"
        healthy = (not pressure and state.send_time_ewma < interval * 0.4
                   and (state.ack_time_ewma is None or state.ack_time_ewma < max(0.08, interval * 0.75))
                   and (state.encoding_time_ewma is None or state.encoding_time_ewma < max(self.encoding_threshold * 0.6, interval * 0.3))
                   and (state.presentation_time_ewma is None or state.presentation_time_ewma < max(0.08, interval)))
        state.pressure_samples = state.pressure_samples + 1 if pressure else 0
        state.healthy_samples = state.healthy_samples + 1 if healthy else 0
        state.quality_direction = 0
        elapsed = now - state.last_adjustment_time
        if pressure and state.pressure_samples >= 3 and elapsed >= self.cooldown_seconds:
            before = self._policy(state)
            minimum_fps = min(5.0, state.limits.fps_ceiling)
            if state.fps > minimum_fps:
                state.fps = max(minimum_fps, round(state.fps * 0.8, 1))
            elif can_resize and state.resolution_index < len(state.limits.scales) - 1:
                state.resolution_index += 1
            else:
                state.current_quality = max(state.limits.quality_floor, state.current_quality - self.quality_step)
            state.quality_direction = -1 if state.current_quality < before["quality"] else 0
            state.adjustment_reason = pressure
            state.last_adjustment_time = now
            state.pressure_samples = state.healthy_samples = 0
        elif healthy and state.healthy_samples >= 8 and elapsed >= self.cooldown_seconds * 2:
            before = self._policy(state)
            if state.current_quality < state.limits.quality_ceiling:
                state.current_quality = min(state.limits.quality_ceiling, state.current_quality + self.quality_step)
            elif can_resize and state.resolution_index:
                state.resolution_index -= 1
            elif state.fps < state.limits.fps_ceiling:
                state.fps = min(state.limits.fps_ceiling, round(state.fps + 1, 1))
            state.quality_direction = 1 if state.current_quality > before["quality"] else 0
            state.adjustment_reason = "healthy_delivery"
            state.last_adjustment_time = now
            state.pressure_samples = state.healthy_samples = 0

    @staticmethod
    def _policy(state: ClientQualityState) -> dict:
        return {"profile": state.profile, "quality": state.current_quality,
                "fps": state.fps,
                "resolution_scale": state.limits.scales[state.resolution_index] if state.can_resize else 1.0}

    def get_client_policy(self, client_id: str) -> Optional[dict]:
        with self._lock:
            state = self._clients.get(client_id)
            return self._policy(state) if state else None

    def update_cpu_load(self, cpu_percent: float) -> None:
        if not self._valid_nonnegative(cpu_percent) or cpu_percent > 100:
            return
        with self._lock:
            self._cpu_load = cpu_percent
            self._cpu_available = True

    def set_client_quality(self, client_id: str, quality: int) -> None:
        if not isinstance(quality, int) or isinstance(quality, bool):
            return
        with self._lock:
            state = self._clients.get(client_id)
            if state is not None:
                state.current_quality = max(state.limits.quality_floor, min(state.limits.quality_ceiling, quality))
                state.last_adjustment_time = self._clock()
                state.pressure_samples = state.healthy_samples = 0
                state.quality_direction = 0
                state.adjustment_reason = "quality_requested"

    def get_client_quality(self, client_id: str) -> int:
        with self._lock:
            state = self._clients.get(client_id)
            return state.current_quality if state else self.default_quality

    def _state_snapshot(self, state: ClientQualityState) -> dict:
        def milliseconds(value):
            return None if value is None else round(value * 1000, 2)

        feedback_age = (None if state.last_delivery_at is None
                        else max(0.0, self._clock() - state.last_delivery_at))
        feedback_stale = feedback_age is not None and feedback_age > max(5.0, self.cooldown_seconds * 3)
        return {**self._policy(state),
                "bandwidth_kbps": round(state.bandwidth_ewma * 8 / 1024, 1),
                "encoding_time_ms": milliseconds(state.encoding_time_ewma) or 0.0,
                "send_time_ms": milliseconds(state.send_time_ewma),
                "ack_time_ms": milliseconds(state.ack_time_ewma),
                "presentation_delay_ms": milliseconds(state.presentation_time_ewma),
                "feedback_available": feedback_age is not None and not feedback_stale,
                "feedback_age_ms": milliseconds(feedback_age),
                "feedback_stale": feedback_stale,
                "adjustment_reason": state.adjustment_reason,
                "direction": state.quality_direction,
                "total_frames": state.total_frames, "total_bytes": state.total_bytes}

    def get_client_state(self, client_id: str) -> Optional[dict]:
        with self._lock:
            state = self._clients.get(client_id)
            return self._state_snapshot(state) if state else None

    def get_all_states(self) -> dict:
        with self._lock:
            return {"cpu_load": round(self._cpu_load, 1), "cpu_monitoring_active": self._cpu_available,
                    "active_clients": len(self._clients),
                    "clients": {cid: self._state_snapshot(state) for cid, state in self._clients.items()}}
