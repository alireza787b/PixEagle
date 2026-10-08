# Image fidelity and independent dimensions

Video follows three explicit branches: captured source pixels, analysis pixels,
and delivered display pixels. Tracking preprocessing (including Gaussian blur
and CLAHE) only affects analysis. Classic/Smart overlays are rendered from
analysis coordinates onto source pixels; an annotated low-resolution image is
never enlarged as a substitute for source detail. Raw recording now uses the
source pixels without tracking annotations.

## Opt into native file/RTSP capture

Existing installations keep their capture behavior. Use Config Sync preview/apply
when accepting new settings, then configure and restart through the existing
Dashboard configuration workflow:

```yaml
VideoSource:
  NATIVE_CAPTURE_RESOLUTION: true
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
Streaming:
  STREAM_WIDTH: 1280
  STREAM_HEIGHT: 720
  STREAM_FPS: 20
  STREAM_QUALITY: 80
```

This is an initial **qualification profile**, not a measured performance promise.
The switch removes built-in file/RTSP GStreamer capture scaling. Native OpenCV
file/RTSP input already retains decoded source dimensions. USB/CSI and explicit
custom pipelines retain their selected capture mode; the switch does not guess
a new sensor mode or rewrite custom pipeline strings.

With the switch enabled, CAPTURE dimensions define analysis dimensions, retaining
existing tracker pixel thresholds and normalized coordinates. For example,
1920×1080 source pixels become 640×480 analysis pixels and 1280×720 display
pixels. This intentionally preserves the old analysis coordinate system even
when its aspect ratio differs. The display retains the complete source aspect
ratio without a crop or padding. Rotation/flip is applied once before the split;
analysis axes follow that orientation. Delivery bounds never enlarge source
pixels. A rotated 1080×1920 source fits 1280×720 bounds as 405×720.

Before opting in on an OpenCV input, check its **actual** current analysis size.
OpenCV file/RTSP decoding may previously have used the native dimensions despite
smaller configured capture values. Set CAPTURE dimensions to that existing
analysis size if retaining those pixel-based thresholds is required; reducing
analysis size is a separate tracker qualification change.

New installations use the switch and a 1280×720 delivery ceiling with balanced
quality 70. Existing saved profiles retain their values until Config Sync
preview/apply accepts migration. Filtered area downscaling is used by the Python
resize path; built-in RTSP scaling uses bilinear filtering instead of nearest
neighbour. Native selection metadata continues to advertise `full_frame_scale`
with independent encoded/analysis dimensions and the same capture identity.

## Qualification

Compare the same captured frame with the direct camera decoder, then check
native display detail, all four image edges, rotated frames and retargeting.
Repeat with local Classic, local Smart and camera-owned tracking. Measure FPS,
frame age, encoding/service time and memory before adopting 1080p or higher
quality on the board. Do not infer camera-to-screen latency from backend receipt
age alone. Disabling native capture and restoring the previous delivery settings
is the rollback; no tracker/follower tuning or ownership is automatically changed.
