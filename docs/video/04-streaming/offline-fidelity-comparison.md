# Compare source detail and JPEG delivery

Use this camera-free tool before changing a live profile. It decodes one exact
frame from a local recorded video and compares three explicit pipelines:

- Reconstructed legacy: nearest-neighbour 640×480, Gaussian blur kernel 5,
  luminance CLAHE clip 2/grid 8, JPEG quality 50.
- Candidate: production aspect-fit resize within 1280×720, JPEG quality 80.
- Candidate: production aspect-fit resize within 1920×1080, JPEG quality 80.

The legacy image is **a reconstruction**, not a recording from the old Pi
process. Candidate resizing uses the same helper as production, but the tool
runs no backend, tracker, QGC renderer or network transport. This isolates image
fidelity from those other stages without claiming an end-to-end result.

From the repository root:

```bash
.venv/bin/python tools/compare_video_fidelity.py \
  --video resources/test4.mp4 --frame 300 \
  --output ~/.cache/pixeagle-video-quality/test4-run-1

.venv/bin/python tools/compare_video_fidelity.py \
  --video resources/test9.mp4 --frame 60 \
  --output ~/.cache/pixeagle-video-quality/test9-run-1

.venv/bin/python tools/compare_video_fidelity.py \
  --synthetic-1080p \
  --output ~/.cache/pixeagle-video-quality/synthetic-run-1
```

Outputs never overwrite earlier evidence. Each directory contains source PNG,
encoded JPEG candidates, identical source-coordinate comparison crops,
`report.json`, and a concise `README.md`. The source frame index is zero-based
and read sequentially to avoid uncertain keyframe seeking. Reports capture file
and pixel hashes, the resize/tool hashes, Git revision, OpenCV/Python versions,
thread count and explicit evidence limitations.

Thirty trials follow three warmups by default. `--trials`, `--fps` and
`--opencv-threads` are configurable. FPS changes only the calculated payload
estimate; this tool does not send video at that rate. Default OpenCV thread
count is one for repeatability. Run comparisons serially and retain host load
information when interpreting service time.

PSNR is calculated only on matching pixel grids. JPEG-only PSNR compares the
prepared image to its JPEG decode. Source-grid PSNR first restores the decoded
candidate to the original source dimensions. CLAHE deliberately changes contrast,
so PSNR is not an operator quality score. Inspect matching crops at equal display
scale. An `exact`/JSON `null` PSNR value denotes zero pixel error.

## Local measurement, 2026-10-08

Serial measurements on this Linux x86_64 development laptop, OpenCV 4.13.0,
Python 3.12.3, one OpenCV thread, 30 trials after warmup:

| Input/profile | JPEG KiB | Estimated payload at 20 FPS | Encode p95 | Total preparation + encode p95 | Source-grid PSNR |
|---|---:|---:|---:|---:|---:|
| test4 frame 300, reconstructed legacy | 15.6 | 2.55 Mbps | 0.36 ms | 3.23 ms | 22.90 dB |
| test4 frame 300, 720p Q80 | 43.6 | 7.14 Mbps | 1.11 ms | 1.23 ms | 46.75 dB |
| test9 frame 60, reconstructed legacy | 13.0 | 2.13 Mbps | 0.32 ms | 3.34 ms | 25.97 dB |
| test9 frame 60, 720p Q80 | 47.5 | 7.78 Mbps | 1.05 ms | 1.17 ms | 46.25 dB |
| Synthetic detail, 720p Q80 | 158.9 | 26.04 Mbps | 1.38 ms | 4.92 ms | 16.48 dB |
| Synthetic detail, 1080p Q80 | 330.3 | 54.12 Mbps | 2.77 ms | 3.06 ms | 25.50 dB |

Both recorded sources are 1280×720. The 1080p bounds therefore produce the same
720p pixels; the separate synthetic fixture supplies genuine 1920×1080 detail.
It deliberately includes fine lines, small text and seeded noise to expose
spatial detail loss and high-entropy JPEG bandwidth demand.

Evidence on the qualification host is under
`~/.cache/pixeagle-video-quality/2026-10-08/`, in
`test4-frame300-serial`, `test9-frame60-serial` and `synthetic1080p-serial`.

The recorded frames show that preserving detail at Q80 costs roughly 7–8 Mbps
of JPEG payload at 20 FPS. An 8 Mbps total link leaves insufficient margin for
transport overhead, telemetry, scene changes or a second client. The synthetic
scene demonstrates why resolution and quality alone cannot guarantee a bitrate.
Adaptation must reduce cadence/dimensions as well as quality when capacity is
limited; compressed inter-frame video needs separate qualification.

These timings exclude capture, tracking, queues, radio/network delay and physical
display. They are not Raspberry Pi capacity measurements. The Pi was thermally
throttled during the follow-up inspection, so no additional board load or hardware
throughput qualification was performed. Recheck thermals before live measurement.
