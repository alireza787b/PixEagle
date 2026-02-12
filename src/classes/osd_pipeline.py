"""
OSD Pipeline Module
===================

Layered OSD composition pipeline for real-time streaming workloads.

Design goals:
- Keep OSD professional while reducing per-frame overhead
- Decouple expensive OSD generation from capture cadence
- Work with both GStreamer and OpenCV capture backends
- Provide runtime metrics for observability and tuning
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .osd_text_renderer import OSDSprite, OSDTextRenderer
from .parameters import Parameters

logger = logging.getLogger(__name__)


class OSDPipeline:
    """
    Real-time OSD composition pipeline with cached layers.

    Layers:
    - static: infrequently changing elements (branding/crosshair)
    - slow_dynamic: low-frequency updates (datetime)
    - dynamic: telemetry/tracker/follower state
    """

    _MODE_ORDER = ("quality", "balanced", "fast")

    def __init__(self, osd_handler: Any):
        self.osd_handler = osd_handler

        # Cached RGBA overlays (legacy overlay path)
        self._static_overlay: Optional[np.ndarray] = None
        self._slow_overlay: Optional[np.ndarray] = None
        self._dynamic_overlay: Optional[np.ndarray] = None
        self._combined_overlay: Optional[np.ndarray] = None

        # ── Sprite cache (new high-performance path) ──
        # Keyed by element identifier (e.g. "name", "mavlink_data.altitude_agl")
        self._sprite_cache: Dict[str, OSDSprite] = {}
        # Flat list rebuilt whenever any sprite changes (avoids dict iteration per frame)
        self._sprite_list: List[OSDSprite] = []
        self._sprite_list_dirty = True

        # Cache invalidation tracking
        self._last_shape: Optional[Tuple[int, int]] = None
        self._last_renderer_id: Optional[int] = None
        self._last_enabled: Optional[bool] = None
        self._last_preset: Optional[str] = None
        self._last_color_mode: Optional[str] = None

        # Update cadence
        self._last_slow_update_ts = 0.0
        self._last_dynamic_update_ts = 0.0

        # Performance stats
        self._compose_samples = deque(maxlen=180)
        self._dynamic_render_samples = deque(maxlen=180)
        self._last_compose_ms = 0.0
        self._last_static_render_ms = 0.0
        self._last_slow_render_ms = 0.0
        self._last_dynamic_render_ms = 0.0
        self._dynamic_updates = 0
        self._slow_updates = 0
        self._dynamic_skips = 0

        # Auto-degrade state
        self._budget_overruns = 0
        self._auto_degrade_active = False
        self._last_degrade_action: Optional[str] = None

        self._load_runtime_config()

    def _load_runtime_config(self) -> None:
        """Reload runtime OSD pipeline parameters from configuration."""
        self.pipeline_mode = str(
            getattr(Parameters, "OSD_PIPELINE_MODE", "layered_realtime")
        ).strip().lower()

        target = str(getattr(Parameters, "OSD_TARGET_LAYER_RESOLUTION", "stream")).strip().lower()
        self.target_resolution = target if target in {"stream", "capture"} else "stream"

        self.dynamic_fps = max(float(getattr(Parameters, "OSD_DYNAMIC_FPS", 10.0)), 0.1)
        self.datetime_fps = max(float(getattr(Parameters, "OSD_DATETIME_FPS", 1.0)), 0.1)

        self.max_render_budget_ms = max(
            float(getattr(Parameters, "OSD_MAX_RENDER_BUDGET_MS", 6.0)),
            0.0,
        )
        self.auto_degrade = bool(getattr(Parameters, "OSD_AUTO_DEGRADE", True))

        min_mode = str(getattr(Parameters, "OSD_AUTO_DEGRADE_MIN_MODE", "balanced")).strip().lower()
        self.auto_degrade_min_mode = min_mode if min_mode in self._MODE_ORDER else "balanced"

        compositor = str(getattr(Parameters, "OSD_COMPOSITOR", "cv2_alpha")).strip().lower()
        self.compositor = compositor if compositor in {"cv2_alpha", "legacy_pil_composite"} else "cv2_alpha"

    def invalidate_cache(self, reason: str = "manual") -> None:
        """Invalidate all cached OSD layers and sprites."""
        self._static_overlay = None
        self._slow_overlay = None
        self._dynamic_overlay = None
        self._combined_overlay = None
        self._sprite_cache.clear()
        self._sprite_list.clear()
        self._sprite_list_dirty = True
        self._last_slow_update_ts = 0.0
        self._last_dynamic_update_ts = 0.0
        logger.debug("OSD pipeline cache invalidated (%s)", reason)

    def _get_renderer(self) -> Any:
        return getattr(self.osd_handler, "renderer", None)

    def _needs_refresh(self, now_ts: float, last_update_ts: float, fps: float) -> bool:
        if fps <= 0:
            return True
        return (now_ts - last_update_ts) >= (1.0 / fps)

    def _refresh_invalidation_state(self, renderer: Any, frame_shape: Tuple[int, int, int]) -> None:
        frame_h, frame_w = frame_shape[:2]
        shape = (frame_w, frame_h)
        enabled = bool(self.osd_handler.is_enabled())
        preset = str(getattr(Parameters, "OSD_PRESET", "professional"))
        renderer_id = id(renderer)

        # Detect color mode change via renderer's color system
        color_mode = ""
        if hasattr(renderer, "_get_color_mode_tag"):
            color_mode = renderer._get_color_mode_tag()

        invalidation_reasons = []
        if self._last_shape != shape:
            invalidation_reasons.append("shape_change")
        if self._last_renderer_id != renderer_id:
            invalidation_reasons.append("renderer_changed")
        if self._last_enabled != enabled:
            invalidation_reasons.append("enabled_changed")
        if self._last_preset != preset:
            invalidation_reasons.append("preset_changed")
        if self._last_color_mode != color_mode:
            invalidation_reasons.append("color_mode_changed")

        if invalidation_reasons:
            self.invalidate_cache(",".join(invalidation_reasons))

        self._last_shape = shape
        self._last_renderer_id = renderer_id
        self._last_enabled = enabled
        self._last_preset = preset
        self._last_color_mode = color_mode

    def _build_layer_overlay(
        self,
        renderer: Any,
        frame_shape: Tuple[int, int, int],
        layer_name: str,
    ) -> Tuple[Optional[np.ndarray], float]:
        start = time.perf_counter()
        overlay = renderer.render_overlay(frame_shape, layer_filter=layer_name)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return overlay, elapsed_ms

    def _maybe_auto_degrade(self, renderer: Any, dynamic_render_ms: float) -> None:
        if not self.auto_degrade or self.max_render_budget_ms <= 0:
            self._budget_overruns = 0
            return

        if dynamic_render_ms <= self.max_render_budget_ms:
            self._budget_overruns = 0
            return

        self._budget_overruns += 1
        if self._budget_overruns < 3:
            return

        current_mode = renderer.get_performance_mode()
        if current_mode not in self._MODE_ORDER:
            return

        current_idx = self._MODE_ORDER.index(current_mode)
        floor_idx = self._MODE_ORDER.index(self.auto_degrade_min_mode)
        next_idx = current_idx + 1

        if next_idx > floor_idx:
            return

        next_mode = self._MODE_ORDER[next_idx]
        if renderer.set_performance_mode(next_mode):
            self._auto_degrade_active = True
            self._last_degrade_action = f"{current_mode}->{next_mode}"
            self._budget_overruns = 0
            self.invalidate_cache("auto_degrade")
            logger.warning(
                "OSD auto-degrade activated: %s (dynamic render %.2f ms > budget %.2f ms)",
                self._last_degrade_action,
                dynamic_render_ms,
                self.max_render_budget_ms,
            )

    def compose(self, frame: np.ndarray) -> np.ndarray:
        """Compose OSD onto a BGR frame using cached sprites (high-performance path).

        Each OSD text element is pre-rendered to a small RGBA sprite and cached.
        Per-frame cost is a single uint16 multiply-accumulate on each sprite's
        tiny ROI (typically 200x40px), plus direct OpenCV drawing for shape
        elements (crosshair, attitude indicator).

        Falls back to legacy overlay path when ``pipeline_mode == "legacy"``
        or ``pipeline_mode == "layered_realtime"`` (backward-compatible overlay
        path preserved as ``_compose_overlay``).
        """
        if frame is None:
            return frame

        self._load_runtime_config()

        # Keep renderer state synchronized with hot-reloaded Parameters.
        configured_enabled = bool(getattr(Parameters, "OSD_ENABLED", True))
        if self.osd_handler.is_enabled() != configured_enabled:
            self.osd_handler.set_enabled(configured_enabled)

        if self.pipeline_mode == "legacy":
            return self.osd_handler.draw_osd(frame)

        if not self.osd_handler.is_enabled():
            return frame

        renderer = self._get_renderer()
        if renderer is None:
            return frame

        self._refresh_invalidation_state(renderer, frame.shape)

        # ── Rebuild stale sprites per layer cadence ──

        now_ts = time.perf_counter()

        # Static layer: rebuild only on cache invalidation
        if not self._sprite_cache:
            start = time.perf_counter()
            self._rebuild_layer_sprites(renderer, frame.shape, "static")
            self._last_static_render_ms = (time.perf_counter() - start) * 1000.0

        # Slow-dynamic layer (datetime, etc.)
        if self._needs_refresh(now_ts, self._last_slow_update_ts, self.datetime_fps):
            start = time.perf_counter()
            self._rebuild_layer_sprites(renderer, frame.shape, "slow_dynamic")
            self._last_slow_render_ms = (time.perf_counter() - start) * 1000.0
            self._last_slow_update_ts = now_ts
            self._slow_updates += 1

        # Dynamic layer (telemetry, tracker/follower status)
        if self._needs_refresh(now_ts, self._last_dynamic_update_ts, self.dynamic_fps):
            start = time.perf_counter()
            self._rebuild_layer_sprites(renderer, frame.shape, "dynamic")
            render_ms = (time.perf_counter() - start) * 1000.0
            self._last_dynamic_render_ms = render_ms
            self._last_dynamic_update_ts = now_ts
            self._dynamic_updates += 1
            self._dynamic_render_samples.append(render_ms)
            self._maybe_auto_degrade(renderer, render_ms)
        else:
            self._dynamic_skips += 1

        # ── Compose onto frame ──

        compose_start = time.perf_counter()

        # 1. Draw non-spriteable elements (crosshair, attitude indicator) directly
        renderer.draw_direct_elements(frame, layer_filter=None)

        # 2. Blit all cached sprites
        if self._sprite_list_dirty:
            self._sprite_list = list(self._sprite_cache.values())
            self._sprite_list_dirty = False

        OSDTextRenderer.blit_sprites(frame, self._sprite_list)

        self._last_compose_ms = (time.perf_counter() - compose_start) * 1000.0
        self._compose_samples.append(self._last_compose_ms)

        return frame

    def _rebuild_layer_sprites(
        self,
        renderer: Any,
        frame_shape: Tuple[int, int, int],
        layer_name: str,
    ) -> None:
        """Rebuild sprites for a single layer, updating cache only on change."""
        new_sprites = renderer.get_element_sprites(frame_shape, layer_filter=layer_name)

        # Remove sprites from this layer that no longer exist
        stale_keys = [
            k for k in self._sprite_cache
            if k in self._sprite_cache
            and renderer._resolve_element_layer(
                k.split(".")[0],
                renderer.osd_elements.get(k.split(".")[0], {}),
            ) == layer_name
            and k not in new_sprites
        ]
        for k in stale_keys:
            del self._sprite_cache[k]
            self._sprite_list_dirty = True

        # Update sprites that changed (content hash comparison)
        for key, sprite in new_sprites.items():
            cached = self._sprite_cache.get(key)
            if cached is None or cached.content_hash != sprite.content_hash:
                self._sprite_cache[key] = sprite
                self._sprite_list_dirty = True

    def _compose_overlay(self, frame: np.ndarray) -> np.ndarray:
        """Legacy overlay-based composition (preserved for backward compatibility).

        Used when ``pipeline_mode == "layered_realtime"`` before the sprite
        refactor.  Not called in normal operation but kept for reference and
        potential fallback.
        """
        renderer = self._get_renderer()
        if renderer is None:
            return frame

        self._refresh_invalidation_state(renderer, frame.shape)
        layer_state_changed = False

        if self._static_overlay is None:
            self._static_overlay, self._last_static_render_ms = self._build_layer_overlay(
                renderer, frame.shape, "static"
            )
            layer_state_changed = True

        now_ts = time.perf_counter()

        if self._slow_overlay is None or self._needs_refresh(now_ts, self._last_slow_update_ts, self.datetime_fps):
            self._slow_overlay, self._last_slow_render_ms = self._build_layer_overlay(
                renderer, frame.shape, "slow_dynamic"
            )
            self._last_slow_update_ts = now_ts
            self._slow_updates += 1
            layer_state_changed = True

        if self._dynamic_overlay is None or self._needs_refresh(now_ts, self._last_dynamic_update_ts, self.dynamic_fps):
            self._dynamic_overlay, self._last_dynamic_render_ms = self._build_layer_overlay(
                renderer, frame.shape, "dynamic"
            )
            self._last_dynamic_update_ts = now_ts
            self._dynamic_updates += 1
            self._dynamic_render_samples.append(self._last_dynamic_render_ms)
            self._maybe_auto_degrade(renderer, self._last_dynamic_render_ms)
            layer_state_changed = True
        else:
            self._dynamic_skips += 1

        if self._combined_overlay is None or layer_state_changed:
            self._combined_overlay = renderer.combine_overlays_rgba(
                (self._static_overlay, self._slow_overlay, self._dynamic_overlay)
            )

        compose_start = time.perf_counter()
        out = renderer.composite_overlay_rgba(frame, self._combined_overlay, method=self.compositor)
        self._last_compose_ms = (time.perf_counter() - compose_start) * 1000.0
        self._compose_samples.append(self._last_compose_ms)
        return out

    @staticmethod
    def _mean(values: deque) -> float:
        if not values:
            return 0.0
        return float(sum(values) / len(values))

    @staticmethod
    def _p95(values: deque) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = int(round(0.95 * (len(ordered) - 1)))
        return float(ordered[idx])

    def get_stats(self) -> Dict[str, Any]:
        """Get OSD pipeline runtime metrics."""
        renderer = self._get_renderer()
        current_mode = renderer.get_performance_mode() if renderer else "unknown"
        return {
            "pipeline_mode": self.pipeline_mode,
            "target_resolution": self.target_resolution,
            "compositor": self.compositor,
            "dynamic_fps_target": self.dynamic_fps,
            "datetime_fps_target": self.datetime_fps,
            "dynamic_updates": self._dynamic_updates,
            "slow_updates": self._slow_updates,
            "dynamic_skips": self._dynamic_skips,
            "compose_ms_last": self._last_compose_ms,
            "compose_ms_avg": self._mean(self._compose_samples),
            "compose_ms_p95": self._p95(self._compose_samples),
            "static_render_ms_last": self._last_static_render_ms,
            "slow_render_ms_last": self._last_slow_render_ms,
            "dynamic_render_ms_last": self._last_dynamic_render_ms,
            "dynamic_render_ms_avg": self._mean(self._dynamic_render_samples),
            "dynamic_render_ms_p95": self._p95(self._dynamic_render_samples),
            "render_budget_ms": self.max_render_budget_ms,
            "auto_degrade_enabled": self.auto_degrade,
            "auto_degrade_active": self._auto_degrade_active,
            "auto_degrade_last_action": self._last_degrade_action,
            "performance_mode": current_mode,
            "sprite_cache_count": len(self._sprite_cache),
            "static_cache_valid": self._static_overlay is not None,
            "dynamic_cache_valid": self._dynamic_overlay is not None,
            "slow_cache_valid": self._slow_overlay is not None,
            "combined_cache_valid": self._combined_overlay is not None,
        }
