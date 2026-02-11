# src/classes/adaptive_quality_engine.py
"""
Unified adaptive quality engine for all JPEG streaming paths.

Considers three signals:
1. Network bandwidth (per-client EWMA)
2. Encoding time (per-client EWMA — reflects hardware encoding speed)
3. CPU load (global, via psutil)

Uses hysteresis (cooldown period) to prevent quality oscillation.
Conservative strategy: if ANY signal says reduce, reduce.
"""

import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict

logger = logging.getLogger(__name__)


@dataclass
class ClientQualityState:
    """Per-client adaptive quality state."""
    client_id: str
    current_quality: int
    bandwidth_ewma: float = 0.0        # bytes/sec, EWMA-smoothed
    encoding_time_ewma: float = 0.0    # seconds, EWMA-smoothed
    last_adjustment_time: float = 0.0
    frames_since_adjustment: int = 0
    quality_direction: int = 0          # +1 increasing, -1 decreasing, 0 stable
    total_frames: int = 0
    total_bytes: int = 0


class AdaptiveQualityEngine:
    """
    Unified quality engine shared across HTTP and WebSocket streaming paths.

    Each streaming client gets a ClientQualityState. Global signals (CPU load)
    affect all clients equally. Quality adjustments respect a cooldown period
    to prevent oscillation.

    All thresholds are configurable via Parameters (loaded at init).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._clients: Dict[str, ClientQualityState] = {}
        self._cpu_load: float = 0.0
        self._cpu_available: bool = False

        # Load config with safe defaults
        self._load_config()

    def _load_config(self) -> None:
        """Load all thresholds from Parameters with safe fallbacks."""
        try:
            from classes.parameters import Parameters
            self.min_quality = getattr(Parameters, 'MIN_QUALITY', 20)
            self.max_quality = getattr(Parameters, 'MAX_QUALITY', 95)
            self.default_quality = getattr(Parameters, 'STREAM_QUALITY', 50)
            self.quality_step = getattr(Parameters, 'QUALITY_STEP_ADAPTIVE', 5)
            self.bandwidth_alpha = getattr(Parameters, 'BANDWIDTH_EWMA_ALPHA', 0.3)
            self.encoding_alpha = getattr(Parameters, 'ENCODING_EWMA_ALPHA', 0.2)
            self.cooldown_seconds = getattr(Parameters, 'QUALITY_COOLDOWN_SECONDS', 2.0)
            self.target_bw_low = getattr(Parameters, 'TARGET_BANDWIDTH_LOW_KBPS', 50) * 1024
            self.target_bw_high = getattr(Parameters, 'TARGET_BANDWIDTH_HIGH_KBPS', 200) * 1024
            self.cpu_high = getattr(Parameters, 'CPU_THRESHOLD_HIGH', 80)
            self.cpu_low = getattr(Parameters, 'CPU_THRESHOLD_LOW', 60)
            self.encoding_threshold = getattr(Parameters, 'ENCODING_TIME_THRESHOLD_MS', 20) / 1000.0
            self.stream_fps = getattr(Parameters, 'STREAM_FPS', 10)
        except Exception:
            # Absolute fallbacks if Parameters not available
            self.min_quality = 20
            self.max_quality = 95
            self.default_quality = 50
            self.quality_step = 5
            self.bandwidth_alpha = 0.3
            self.encoding_alpha = 0.2
            self.cooldown_seconds = 2.0
            self.target_bw_low = 50 * 1024
            self.target_bw_high = 200 * 1024
            self.cpu_high = 80
            self.cpu_low = 60
            self.encoding_threshold = 0.020
            self.stream_fps = 10

    def register_client(self, client_id: str, initial_quality: Optional[int] = None) -> None:
        """Register a new streaming client."""
        quality = initial_quality if initial_quality is not None else self.default_quality
        with self._lock:
            self._clients[client_id] = ClientQualityState(
                client_id=client_id,
                current_quality=max(self.min_quality, min(self.max_quality, quality)),
                last_adjustment_time=time.monotonic(),
            )

    def unregister_client(self, client_id: str) -> None:
        """Remove a streaming client."""
        with self._lock:
            self._clients.pop(client_id, None)

    def report_frame_sent(
        self, client_id: str, frame_size_bytes: int, encoding_time_seconds: float
    ) -> int:
        """
        Report that a frame was sent to a client.

        Updates bandwidth/encoding EWMA and returns the quality level
        to use for the NEXT frame.

        Args:
            client_id: The streaming client identifier
            frame_size_bytes: Size of the encoded JPEG in bytes
            encoding_time_seconds: Time taken to encode the frame

        Returns:
            Quality level (int) for the next frame.
        """
        now = time.monotonic()

        with self._lock:
            state = self._clients.get(client_id)
            if state is None:
                return self.default_quality

            state.total_frames += 1
            state.total_bytes += frame_size_bytes

            # Update EWMA bandwidth estimate (frame_size * fps = estimated throughput)
            estimated_bw = frame_size_bytes * self.stream_fps
            if state.bandwidth_ewma > 0:
                state.bandwidth_ewma = (
                    self.bandwidth_alpha * estimated_bw
                    + (1 - self.bandwidth_alpha) * state.bandwidth_ewma
                )
            else:
                state.bandwidth_ewma = estimated_bw

            # Update EWMA encoding time
            if state.encoding_time_ewma > 0:
                state.encoding_time_ewma = (
                    self.encoding_alpha * encoding_time_seconds
                    + (1 - self.encoding_alpha) * state.encoding_time_ewma
                )
            else:
                state.encoding_time_ewma = encoding_time_seconds

            state.frames_since_adjustment += 1

            # Respect cooldown period
            if (now - state.last_adjustment_time) < self.cooldown_seconds:
                return state.current_quality

            # Calculate adjustment
            adjustment = self._calculate_adjustment(state)

            if adjustment != 0:
                new_quality = max(
                    self.min_quality,
                    min(self.max_quality, state.current_quality + adjustment),
                )
                if new_quality != state.current_quality:
                    old_quality = state.current_quality
                    state.quality_direction = 1 if adjustment > 0 else -1
                    state.current_quality = new_quality
                    state.last_adjustment_time = now
                    state.frames_since_adjustment = 0
                    logger.debug(
                        f"Quality {old_quality}->{new_quality} for {client_id} "
                        f"(bw={state.bandwidth_ewma / 1024:.0f}KB/s, "
                        f"enc={state.encoding_time_ewma * 1000:.1f}ms, "
                        f"cpu={self._cpu_load:.0f}%)"
                    )
            else:
                state.quality_direction = 0

            return state.current_quality

    def _calculate_adjustment(self, state: ClientQualityState) -> int:
        """
        Calculate quality adjustment based on all signals.

        Conservative: if ANY signal says reduce, we reduce.
        Only increase if ALL signals are favorable.
        """
        signals = []

        # Signal 1: Network bandwidth
        if state.bandwidth_ewma > self.target_bw_high:
            signals.append(+self.quality_step)
        elif state.bandwidth_ewma < self.target_bw_low:
            signals.append(-self.quality_step)

        # Signal 2: Encoding time (hardware performance)
        if state.encoding_time_ewma > self.encoding_threshold:
            signals.append(-self.quality_step)

        # Signal 3: CPU load (global)
        if self._cpu_available:
            if self._cpu_load > self.cpu_high:
                signals.append(-self.quality_step)
            elif self._cpu_load < self.cpu_low:
                signals.append(+max(1, self.quality_step // 2))

        if not signals:
            return 0

        # Conservative: if any signal is negative, reduce
        if any(s < 0 for s in signals):
            return min(signals)  # Most aggressive reduction

        # All signals positive: take the smallest increase
        return min(signals)

    def update_cpu_load(self, cpu_percent: float) -> None:
        """
        Called periodically by a background task with current CPU usage.

        Args:
            cpu_percent: CPU usage percentage (0-100)
        """
        self._cpu_load = cpu_percent
        self._cpu_available = True

    def set_client_quality(self, client_id: str, quality: int) -> None:
        """
        Manually set quality for a client (e.g., from client-side request).
        Resets the cooldown timer.
        """
        with self._lock:
            state = self._clients.get(client_id)
            if state is not None:
                state.current_quality = max(self.min_quality, min(self.max_quality, quality))
                state.last_adjustment_time = time.monotonic()
                state.quality_direction = 0

    def get_client_quality(self, client_id: str) -> int:
        """Get current quality for a client."""
        with self._lock:
            state = self._clients.get(client_id)
            return state.current_quality if state else self.default_quality

    def get_client_state(self, client_id: str) -> Optional[dict]:
        """Get detailed state for a client (for status API)."""
        with self._lock:
            state = self._clients.get(client_id)
            if state is None:
                return None
            return {
                'quality': state.current_quality,
                'bandwidth_kbps': round(state.bandwidth_ewma * 8 / 1024, 1),
                'encoding_time_ms': round(state.encoding_time_ewma * 1000, 2),
                'direction': state.quality_direction,
                'total_frames': state.total_frames,
                'total_bytes': state.total_bytes,
            }

    def get_all_states(self) -> dict:
        """Get engine-wide state (for status API)."""
        with self._lock:
            return {
                'cpu_load': round(self._cpu_load, 1),
                'cpu_monitoring_active': self._cpu_available,
                'active_clients': len(self._clients),
                'clients': {
                    cid: {
                        'quality': s.current_quality,
                        'bandwidth_kbps': round(s.bandwidth_ewma * 8 / 1024, 1),
                        'encoding_time_ms': round(s.encoding_time_ewma * 1000, 2),
                        'direction': s.quality_direction,
                    }
                    for cid, s in self._clients.items()
                },
            }
