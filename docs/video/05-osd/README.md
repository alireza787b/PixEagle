# On-screen display

PixEagle draws telemetry, tracker/follower status and optional camera overlays
on its display pixels. Analysis pixels remain separate. The same encoded OSD
is visible in Dashboard and native QGC video; it is not a client-specific UI.

## Configure

Use Dashboard configuration or the canonical YAML:

```yaml
OSD:
  OSD_ENABLED: true
  OSD_PRESET: professional
  OSD_PERFORMANCE_MODE: balanced
  OSD_PIPELINE_MODE: layered_realtime
  OSD_TARGET_LAYER_RESOLUTION: stream
```

Presets are in `configs/osd_presets`. They control element visibility, semantic
colors, readable text scales, anchors and resolution-scaled spacing. Use a
minimal preset when the video link cannot carry readable detailed telemetry.
The OSD toggle changes visibility; it does not change flight safety settings.

The layered pipeline caches static, datetime and dynamic telemetry sprites.
Automatic degradation can reduce rendering cost without reverting to tiny,
fixed-resolution text. Final readability depends on the delivered resolution,
compression, screen size and scene contrast; it requires operator review.

- [Text sizing, contrast and modes](text-rendering.md)
- [Renderer](osd-renderer.md)
- [Layout](layout-manager.md)
- [Streaming policy and measurements](../04-streaming/streaming-optimizer.md)
