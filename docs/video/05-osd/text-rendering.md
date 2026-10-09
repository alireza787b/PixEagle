# OSD text rendering

`OSDTextRenderer` renders text for `OSDRenderer` and its cached sprite pipeline.
All modes use top-left layout coordinates and measure the font they actually
render. Text, preset offsets, and their spacing scale from a 640×480 reference.
Small labels have a nominal 16-pixel font-size floor at that reference, scaled
with the frame dimensions; `GLOBAL_SETTINGS.base_font_scale` remains the
preset's overall size override. Narrow frames use the smaller dimension ratio.

## Rendering modes

- **Balanced:** bundled or system TrueType fonts with Pillow's native outlines.
- **Quality:** TrueType fonts with the configured outline/shadow treatment.
- **Fast:** resolution-scaled, antialiased OpenCV text. It uses the same nominal
  sizing contract; it does not revert to fixed tiny fonts at 720p or 1080p.

Font discovery checks `resources/fonts` first, then platform font locations.
Missing TrueType fonts use the measured OpenCV fallback. Text measurements are
cached separately by mode and invalidated on resolution changes. The cache is
bounded to 512 entries so changing telemetry cannot grow it indefinitely.

## Presets and configuration

Select the preset and renderer in the canonical backend configuration:

```yaml
OSD:
  OSD_ENABLED: true
  OSD_PRESET: professional
  OSD_PERFORMANCE_MODE: balanced
  OSD_PIPELINE_MODE: layered_realtime
  OSD_TARGET_LAYER_RESOLUTION: stream
```

Presets live in `configs/osd_presets/<name>.yaml`. Their `ELEMENTS` configure
visibility, text scale, semantic color roles, anchor, offset and style. An
`offset` is expressed in pixels at the 640×480 reference; percentage positions
remain percentages. Use `GLOBAL_SETTINGS.base_font_scale` for overall size.
Outlined text and compact background plates keep contrast across camera scenes.

The stream path renders OSD at its delivery ceiling before per-client JPEG
adaptation. Smaller negotiated copies also shrink baked-in text; sufficiently
low resolutions cannot preserve all labels. Do not claim readability from
resolution alone: review the final delivered frame at the intended screen size
and compression. Prefer a reduced OSD preset on very narrow links.

## Performance and validation

The layered pipeline caches individual text sprites and only rebuilds changing
layers at their configured cadence. It applies small sprite regions rather than
converting the entire image for each label. Automatic performance degradation
can choose Fast without changing the coordinate/sizing contract.

Run the real renderer regressions:

```bash
PYTHONPATH=src pytest tests/unit/osd/test_osd_resolution_contract.py \
  tests/unit/core_app/test_osd_pipeline_multi_output.py
```

They cover mode-specific measurements, 480p/720p/1080p sizing, top-left drawing,
preset offset scaling, mode changes, and bounded changing-telemetry caches.
Physical screen readability remains an operator checkpoint.
