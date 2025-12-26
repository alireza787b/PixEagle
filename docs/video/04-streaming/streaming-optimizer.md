# Streaming Optimizer

> Adaptive quality and caching for efficient streaming

## Overview

The StreamingOptimizer manages video encoding efficiency across multiple clients, implementing frame caching, quality adaptation, and bandwidth management.

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    Streaming Optimizer                          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Frame Input                    Cached Outputs                  │
│  ───────────                    ──────────────                  │
│                                                                 │
│  ┌─────────┐    ┌──────────────────────────────────┐           │
│  │ BGR     │───▶│  Frame Cache                     │           │
│  │ Frame   │    │  ┌────────────────────────────┐  │           │
│  └─────────┘    │  │ Q=90: encoded_high        │──┼──▶ Client1│
│                 │  │ Q=70: encoded_medium      │──┼──▶ Client2│
│                 │  │ Q=50: encoded_low         │──┼──▶ Client3│
│                 │  └────────────────────────────┘  │           │
│                 └──────────────────────────────────┘           │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

## Configuration

```yaml
Streaming:
  ENABLE_OPTIMIZER: true
  CACHE_SIZE: 3                    # Number of quality levels to cache
  QUALITY_LEVELS: [90, 70, 50]     # JPEG quality presets
  ADAPTIVE_QUALITY: true           # Enable bandwidth adaptation
  MIN_QUALITY: 30                  # Minimum quality floor
  MAX_QUALITY: 95                  # Maximum quality ceiling
  TARGET_BITRATE: 2000             # kbps target
```

## Implementation

### StreamingOptimizer Class

```python
import cv2
import numpy as np
from collections import OrderedDict
from typing import Dict, Optional, Tuple
import time
import threading

class StreamingOptimizer:
    """
    Optimizes video streaming through caching and quality adaptation.

    Attributes:
        quality_levels: List of JPEG quality presets
        frame_cache: LRU cache of encoded frames
        bandwidth_stats: Per-client bandwidth tracking
    """

    def __init__(
        self,
        quality_levels: list = [90, 70, 50],
        cache_size: int = 3,
        target_bitrate: int = 2000
    ):
        self.quality_levels = sorted(quality_levels, reverse=True)
        self.cache_size = cache_size
        self.target_bitrate = target_bitrate * 1000  # Convert to bps

        # Frame cache: {frame_id: {quality: encoded_bytes}}
        self._cache: OrderedDict = OrderedDict()
        self._cache_lock = threading.Lock()
        self._max_cache_frames = 5

        # Per-client stats
        self._client_stats: Dict[str, ClientStats] = {}

        # Current frame
        self._current_frame_id = 0
        self._last_frame_time = time.time()

    def encode_frame(
        self,
        frame: np.ndarray,
        quality: Optional[int] = None,
        client_id: Optional[str] = None
    ) -> bytes:
        """
        Encode frame with caching.

        Args:
            frame: BGR numpy array
            quality: JPEG quality (uses adaptive if None)
            client_id: Client identifier for adaptive quality

        Returns:
            JPEG encoded bytes
        """
        frame_id = id(frame)

        # Determine quality
        if quality is None:
            quality = self._get_adaptive_quality(client_id)

        # Snap to nearest quality level
        quality = self._snap_quality(quality)

        # Check cache
        with self._cache_lock:
            if frame_id in self._cache:
                if quality in self._cache[frame_id]:
                    return self._cache[frame_id][quality]

        # Encode
        _, buffer = cv2.imencode(
            '.jpg',
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality]
        )
        encoded = buffer.tobytes()

        # Update cache
        with self._cache_lock:
            if frame_id not in self._cache:
                self._cache[frame_id] = {}
            self._cache[frame_id][quality] = encoded

            # Evict old frames
            while len(self._cache) > self._max_cache_frames:
                self._cache.popitem(last=False)

        # Update stats
        if client_id:
            self._update_stats(client_id, len(encoded))

        return encoded

    def _snap_quality(self, quality: int) -> int:
        """Snap to nearest quality level."""
        if not self.quality_levels:
            return quality
        return min(self.quality_levels, key=lambda q: abs(q - quality))

    def _get_adaptive_quality(self, client_id: Optional[str]) -> int:
        """Calculate adaptive quality based on client bandwidth."""
        if not client_id or client_id not in self._client_stats:
            return self.quality_levels[0]  # Default to highest

        stats = self._client_stats[client_id]

        # Calculate current bitrate
        current_bitrate = stats.get_bitrate()

        # Adjust quality
        if current_bitrate > self.target_bitrate * 1.2:
            # Reduce quality
            return self._lower_quality(stats.current_quality)
        elif current_bitrate < self.target_bitrate * 0.8:
            # Increase quality
            return self._raise_quality(stats.current_quality)

        return stats.current_quality

    def _lower_quality(self, current: int) -> int:
        """Get next lower quality level."""
        for q in self.quality_levels:
            if q < current:
                return q
        return min(self.quality_levels)

    def _raise_quality(self, current: int) -> int:
        """Get next higher quality level."""
        for q in reversed(self.quality_levels):
            if q > current:
                return q
        return max(self.quality_levels)

    def _update_stats(self, client_id: str, bytes_sent: int):
        """Update client statistics."""
        if client_id not in self._client_stats:
            self._client_stats[client_id] = ClientStats(
                quality=self.quality_levels[0]
            )
        self._client_stats[client_id].add_bytes(bytes_sent)

    def get_cached_qualities(self, frame: np.ndarray) -> list:
        """Get list of cached quality levels for frame."""
        frame_id = id(frame)
        with self._cache_lock:
            if frame_id in self._cache:
                return list(self._cache[frame_id].keys())
        return []

    def clear_cache(self):
        """Clear frame cache."""
        with self._cache_lock:
            self._cache.clear()

    def get_stats(self) -> dict:
        """Get optimizer statistics."""
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


class ClientStats:
    """Per-client streaming statistics."""

    def __init__(self, quality: int = 80):
        self.current_quality = quality
        self.bytes_history: list = []
        self.time_history: list = []
        self.window_size = 30  # 1 second at 30fps

    def add_bytes(self, byte_count: int):
        """Record bytes sent."""
        self.bytes_history.append(byte_count)
        self.time_history.append(time.time())

        # Trim old data
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
```

### Integration with Streaming

```python
from streaming_optimizer import StreamingOptimizer

optimizer = StreamingOptimizer(
    quality_levels=[90, 70, 50],
    target_bitrate=2000
)

# In streaming handler
async def stream_frame(client_id: str):
    frame = video_handler.current_osd_frame

    # Get optimized encoded frame
    encoded = optimizer.encode_frame(
        frame,
        client_id=client_id
    )

    return encoded
```

## Quality Adaptation Algorithm

```python
def adapt_quality(client_stats, target_bitrate):
    """
    Adaptive quality algorithm.

    1. Measure actual bitrate over sliding window
    2. Compare to target bitrate
    3. Adjust quality up/down based on headroom
    4. Apply smoothing to avoid oscillation
    """
    current_bitrate = client_stats.get_bitrate()
    ratio = current_bitrate / target_bitrate

    if ratio > 1.2:
        # Significantly over target, reduce quality
        new_quality = current_quality - 15
    elif ratio > 1.05:
        # Slightly over, reduce slowly
        new_quality = current_quality - 5
    elif ratio < 0.8:
        # Significantly under, increase quality
        new_quality = current_quality + 10
    elif ratio < 0.95:
        # Slightly under, increase slowly
        new_quality = current_quality + 5
    else:
        # On target, maintain
        new_quality = current_quality

    return clamp(new_quality, 30, 95)
```

## Frame Caching Strategy

### Cache Benefits

1. **Multi-client efficiency**: Encode once, serve many
2. **Quality level reuse**: Common quality levels are cached
3. **Reduced CPU**: Avoid redundant encoding

### Cache Eviction

```python
# LRU eviction
while len(self._cache) > self._max_cache_frames:
    oldest_frame_id = next(iter(self._cache))
    del self._cache[oldest_frame_id]
```

### Cache Key Design

```python
# Frame identity + quality = cache key
cache_key = (id(frame), quality)

# Alternative: frame hash for content-based dedup
cache_key = (hash(frame.tobytes()), quality)
```

## Performance Metrics

### Metrics to Monitor

| Metric | Target | Action if Exceeded |
|--------|--------|-------------------|
| Cache hit rate | >80% | Increase cache size |
| Encode time | <10ms | Lower resolution |
| Bitrate variance | <20% | Adjust adaptation speed |
| Client latency | <100ms | Lower quality floor |

### Monitoring API

```python
stats = optimizer.get_stats()
print(f"Cache frames: {stats['cache_frames']}")
print(f"Cache size: {stats['cache_bytes'] / 1024:.1f} KB")
print(f"Active clients: {stats['client_count']}")
```

## Troubleshooting

### High CPU Usage

1. Reduce number of quality levels
2. Increase cache size
3. Lower maximum quality

### Poor Quality

1. Increase target bitrate
2. Raise minimum quality floor
3. Check network bandwidth

### Cache Misses

1. Increase max cache frames
2. Use fewer quality levels
3. Check frame identity consistency
