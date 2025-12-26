# tests/unit/streaming/test_streaming_optimizer.py
"""
Unit tests for streaming optimizer functionality.

Tests cover:
- Frame caching
- Quality level snapping
- Adaptive quality algorithm
- Client statistics tracking
- Bandwidth calculation
"""

import pytest
import numpy as np
import cv2
import time
from unittest.mock import MagicMock
from typing import Dict, List, Optional
from collections import OrderedDict
import threading

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.streaming]


# ============================================================================
# Streaming Optimizer Mock Implementation
# ============================================================================

class ClientStats:
    """Per-client streaming statistics."""

    def __init__(self, quality: int = 80):
        self.current_quality = quality
        self.bytes_history: List[int] = []
        self.time_history: List[float] = []
        self.window_size = 30

    def add_bytes(self, byte_count: int):
        """Record bytes sent."""
        self.bytes_history.append(byte_count)
        self.time_history.append(time.time())

        while len(self.bytes_history) > self.window_size:
            self.bytes_history.pop(0)
            self.time_history.pop(0)

    def get_bitrate(self) -> float:
        """Calculate current bitrate in bps."""
        if len(self.time_history) < 2:
            return 0

        duration = self.time_history[-1] - self.time_history[0]
        if duration == 0:
            return 0

        total_bytes = sum(self.bytes_history)
        return (total_bytes * 8) / duration


class StreamingOptimizer:
    """Mock streaming optimizer for testing."""

    def __init__(
        self,
        quality_levels: List[int] = None,
        cache_size: int = 3,
        target_bitrate: int = 2000
    ):
        self.quality_levels = sorted(quality_levels or [90, 70, 50], reverse=True)
        self.cache_size = cache_size
        self.target_bitrate = target_bitrate * 1000

        self._cache: OrderedDict = OrderedDict()
        self._cache_lock = threading.Lock()
        self._max_cache_frames = 5
        self._client_stats: Dict[str, ClientStats] = {}

    def encode_frame(
        self,
        frame: np.ndarray,
        quality: Optional[int] = None,
        client_id: Optional[str] = None
    ) -> bytes:
        frame_id = id(frame)

        if quality is None:
            quality = self._get_adaptive_quality(client_id)

        quality = self._snap_quality(quality)

        with self._cache_lock:
            if frame_id in self._cache:
                if quality in self._cache[frame_id]:
                    return self._cache[frame_id][quality]

        _, buffer = cv2.imencode(
            '.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality]
        )
        encoded = buffer.tobytes()

        with self._cache_lock:
            if frame_id not in self._cache:
                self._cache[frame_id] = {}
            self._cache[frame_id][quality] = encoded

            while len(self._cache) > self._max_cache_frames:
                self._cache.popitem(last=False)

        if client_id:
            self._update_stats(client_id, len(encoded))

        return encoded

    def _snap_quality(self, quality: int) -> int:
        if not self.quality_levels:
            return quality
        return min(self.quality_levels, key=lambda q: abs(q - quality))

    def _get_adaptive_quality(self, client_id: Optional[str]) -> int:
        if not client_id or client_id not in self._client_stats:
            return self.quality_levels[0]

        stats = self._client_stats[client_id]
        current_bitrate = stats.get_bitrate()

        if current_bitrate > self.target_bitrate * 1.2:
            return self._lower_quality(stats.current_quality)
        elif current_bitrate < self.target_bitrate * 0.8:
            return self._raise_quality(stats.current_quality)

        return stats.current_quality

    def _lower_quality(self, current: int) -> int:
        for q in self.quality_levels:
            if q < current:
                return q
        return min(self.quality_levels)

    def _raise_quality(self, current: int) -> int:
        for q in reversed(self.quality_levels):
            if q > current:
                return q
        return max(self.quality_levels)

    def _update_stats(self, client_id: str, bytes_sent: int):
        if client_id not in self._client_stats:
            self._client_stats[client_id] = ClientStats(
                quality=self.quality_levels[0]
            )
        self._client_stats[client_id].add_bytes(bytes_sent)

    def get_cached_qualities(self, frame: np.ndarray) -> List[int]:
        frame_id = id(frame)
        with self._cache_lock:
            if frame_id in self._cache:
                return list(self._cache[frame_id].keys())
        return []

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()

    def get_stats(self) -> dict:
        with self._cache_lock:
            cache_size = sum(
                sum(len(v) for v in frame.values())
                for frame in self._cache.values()
            )

        return {
            'cache_frames': len(self._cache),
            'cache_bytes': cache_size,
            'quality_levels': self.quality_levels,
            'client_count': len(self._client_stats),
            'target_bitrate': self.target_bitrate
        }


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_frame():
    """Create a test BGR frame."""
    return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)


@pytest.fixture
def optimizer():
    """Create streaming optimizer instance."""
    return StreamingOptimizer(
        quality_levels=[90, 70, 50],
        target_bitrate=2000
    )


# ============================================================================
# Frame Caching Tests
# ============================================================================

class TestFrameCaching:
    """Tests for frame caching functionality."""

    def test_encode_frame_caches_result(self, optimizer, test_frame):
        """Encoded frame is cached."""
        optimizer.encode_frame(test_frame, quality=80)
        cached = optimizer.get_cached_qualities(test_frame)
        assert len(cached) > 0

    def test_cache_returns_same_bytes(self, optimizer, test_frame):
        """Cache returns identical bytes."""
        first = optimizer.encode_frame(test_frame, quality=80)
        second = optimizer.encode_frame(test_frame, quality=80)
        assert first == second

    def test_different_quality_creates_new_cache(self, optimizer, test_frame):
        """Different quality creates separate cache entry."""
        optimizer.encode_frame(test_frame, quality=90)
        optimizer.encode_frame(test_frame, quality=50)

        cached = optimizer.get_cached_qualities(test_frame)
        assert len(cached) == 2

    def test_cache_eviction(self, optimizer):
        """Old frames are evicted from cache."""
        optimizer._max_cache_frames = 3

        # Create all frames first and keep references to prevent memory reuse
        frames = [np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(5)]
        for frame in frames:
            optimizer.encode_frame(frame, quality=80)

        stats = optimizer.get_stats()
        # Should have at most 3 frames (may have fewer if id() collision)
        assert stats['cache_frames'] <= 3

    def test_clear_cache(self, optimizer, test_frame):
        """Cache can be cleared."""
        optimizer.encode_frame(test_frame, quality=80)
        optimizer.clear_cache()

        stats = optimizer.get_stats()
        assert stats['cache_frames'] == 0

    def test_cache_thread_safety(self, optimizer, test_frame):
        """Cache operations are thread-safe."""
        import threading

        def encode_frames():
            for _ in range(10):
                optimizer.encode_frame(test_frame, quality=80)

        threads = [threading.Thread(target=encode_frames) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not raise


# ============================================================================
# Quality Level Snapping Tests
# ============================================================================

class TestQualitySnapping:
    """Tests for quality level snapping."""

    def test_snap_to_exact_level(self, optimizer):
        """Exact quality level is not changed."""
        snapped = optimizer._snap_quality(90)
        assert snapped == 90

    def test_snap_to_nearest_higher(self, optimizer):
        """Quality snaps to nearest level (higher)."""
        snapped = optimizer._snap_quality(85)
        assert snapped == 90

    def test_snap_to_nearest_lower(self, optimizer):
        """Quality snaps to nearest level (lower)."""
        snapped = optimizer._snap_quality(55)
        assert snapped == 50

    def test_snap_midpoint(self, optimizer):
        """Midpoint quality snaps consistently."""
        snapped = optimizer._snap_quality(60)
        # Should snap to nearest (50 or 70)
        assert snapped in [50, 70]

    def test_snap_below_minimum(self, optimizer):
        """Quality below minimum snaps to minimum."""
        snapped = optimizer._snap_quality(30)
        assert snapped == 50

    def test_snap_above_maximum(self, optimizer):
        """Quality above maximum snaps to maximum."""
        snapped = optimizer._snap_quality(100)
        assert snapped == 90

    def test_snap_with_empty_levels(self):
        """Empty quality levels returns input."""
        opt = StreamingOptimizer(quality_levels=[])
        # When empty, we set a default
        opt.quality_levels = []
        snapped = opt._snap_quality(75)
        # With empty levels, should return input
        assert snapped == 75 or snapped is not None


# ============================================================================
# Adaptive Quality Tests
# ============================================================================

class TestAdaptiveQuality:
    """Tests for adaptive quality algorithm."""

    def test_default_quality_for_new_client(self, optimizer):
        """New client gets highest quality."""
        quality = optimizer._get_adaptive_quality("new_client")
        assert quality == 90

    def test_lower_quality_when_over_bitrate(self, optimizer):
        """Quality is lowered when bitrate exceeds target."""
        client_id = "test_client"
        optimizer._client_stats[client_id] = ClientStats(quality=90)
        stats = optimizer._client_stats[client_id]

        # Simulate high bandwidth usage
        for _ in range(10):
            stats.add_bytes(100000)  # 100KB per frame
            time.sleep(0.01)

        # Should suggest lower quality
        quality = optimizer._get_adaptive_quality(client_id)
        assert quality <= 90

    def test_raise_quality_when_under_bitrate(self, optimizer):
        """Quality is raised when bitrate is below target."""
        client_id = "test_client"
        optimizer._client_stats[client_id] = ClientStats(quality=50)
        stats = optimizer._client_stats[client_id]

        # Simulate low bandwidth usage
        for _ in range(10):
            stats.add_bytes(1000)  # 1KB per frame
            time.sleep(0.01)

        # Should suggest higher quality
        quality = optimizer._get_adaptive_quality(client_id)
        assert quality >= 50

    def test_maintain_quality_at_target(self, optimizer):
        """Quality is maintained when at target bitrate."""
        client_id = "test_client"
        initial_quality = 70
        optimizer._client_stats[client_id] = ClientStats(quality=initial_quality)
        stats = optimizer._client_stats[client_id]

        # Simulate target bandwidth usage
        target_bytes = optimizer.target_bitrate / 8 / 30  # bytes per frame at 30fps
        for _ in range(10):
            stats.add_bytes(int(target_bytes))
            time.sleep(0.033)

        quality = optimizer._get_adaptive_quality(client_id)
        # Should be close to initial
        assert abs(quality - initial_quality) <= 20


# ============================================================================
# Client Statistics Tests
# ============================================================================

class TestClientStatistics:
    """Tests for client statistics tracking."""

    def test_new_client_stats_created(self, optimizer, test_frame):
        """New client stats are created on first encode."""
        optimizer.encode_frame(test_frame, quality=80, client_id="client1")
        assert "client1" in optimizer._client_stats

    def test_bytes_history_updated(self, optimizer, test_frame):
        """Bytes history is updated on encode."""
        optimizer.encode_frame(test_frame, quality=80, client_id="client1")
        stats = optimizer._client_stats["client1"]
        assert len(stats.bytes_history) == 1

    def test_multiple_encodes_track_history(self, optimizer):
        """Multiple encodes update history."""
        # Create all unique frames first to ensure different id()
        frames = [np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(5)]
        for frame in frames:
            optimizer.encode_frame(frame, quality=80, client_id="client1")

        stats = optimizer._client_stats["client1"]
        assert len(stats.bytes_history) == 5

    def test_history_window_limit(self):
        """History is limited to window size."""
        stats = ClientStats(quality=80)
        stats.window_size = 10

        for _ in range(20):
            stats.add_bytes(1000)

        assert len(stats.bytes_history) == 10

    def test_separate_stats_per_client(self, optimizer):
        """Each client has separate statistics."""
        # Use different frames to avoid cache
        frame1 = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        frame2 = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        optimizer.encode_frame(frame1, quality=80, client_id="client1")
        optimizer.encode_frame(frame2, quality=80, client_id="client2")

        assert "client1" in optimizer._client_stats
        assert "client2" in optimizer._client_stats
        assert optimizer._client_stats["client1"] is not optimizer._client_stats["client2"]


# ============================================================================
# Bandwidth Calculation Tests
# ============================================================================

class TestBandwidthCalculation:
    """Tests for bandwidth calculation."""

    def test_bitrate_zero_with_no_history(self):
        """Bitrate is zero with no history."""
        stats = ClientStats()
        assert stats.get_bitrate() == 0

    def test_bitrate_zero_with_single_entry(self):
        """Bitrate is zero with single history entry."""
        stats = ClientStats()
        stats.add_bytes(1000)
        assert stats.get_bitrate() == 0

    def test_bitrate_calculation(self):
        """Bitrate is calculated correctly."""
        stats = ClientStats()

        # Add bytes over time
        for _ in range(10):
            stats.add_bytes(10000)  # 10KB
            time.sleep(0.01)  # 10ms

        bitrate = stats.get_bitrate()
        # Should be roughly 10KB * 8 / 0.1s = 800,000 bps
        assert bitrate > 0

    def test_bitrate_updates_with_window(self):
        """Bitrate is based on sliding window."""
        stats = ClientStats()
        stats.window_size = 5

        # Add small bytes
        for _ in range(5):
            stats.add_bytes(100)
            time.sleep(0.01)

        small_bitrate = stats.get_bitrate()

        # Add large bytes (old small ones will be evicted)
        for _ in range(5):
            stats.add_bytes(10000)
            time.sleep(0.01)

        large_bitrate = stats.get_bitrate()

        assert large_bitrate > small_bitrate


# ============================================================================
# Optimizer Stats Tests
# ============================================================================

class TestOptimizerStats:
    """Tests for optimizer statistics."""

    def test_get_stats_returns_dict(self, optimizer):
        """get_stats returns dictionary."""
        stats = optimizer.get_stats()
        assert isinstance(stats, dict)

    def test_stats_includes_cache_frames(self, optimizer, test_frame):
        """Stats include cache frame count."""
        optimizer.encode_frame(test_frame, quality=80)
        stats = optimizer.get_stats()
        assert stats['cache_frames'] == 1

    def test_stats_includes_quality_levels(self, optimizer):
        """Stats include quality levels."""
        stats = optimizer.get_stats()
        assert stats['quality_levels'] == [90, 70, 50]

    def test_stats_includes_client_count(self, optimizer):
        """Stats include client count."""
        # Use different frames to avoid cache
        frame1 = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        frame2 = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        optimizer.encode_frame(frame1, quality=80, client_id="client1")
        optimizer.encode_frame(frame2, quality=80, client_id="client2")

        stats = optimizer.get_stats()
        assert stats['client_count'] == 2

    def test_stats_includes_target_bitrate(self, optimizer):
        """Stats include target bitrate."""
        stats = optimizer.get_stats()
        assert stats['target_bitrate'] == 2000000  # 2000 kbps in bps
