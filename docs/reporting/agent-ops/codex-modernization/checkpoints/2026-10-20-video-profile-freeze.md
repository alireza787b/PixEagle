# October 20 video profile and source checkpoint

## Scope and configuration

Freeze the measured baselines in
[Video profile baselines](../../../../video/06-configuration/qualified-profile-baselines.md).
Factory remains video-file/OpenCV, PixEagle CSRT, constant-position following,
no gimbal, circuit breaker and altitude safeguards enabled. Automatic delivery
has a 720p/20 FPS ceiling, 12 FPS/75% startup, JPEG 70–85 and an 8,000 kbps
configured payload budget. It does not require optional GStreamer.

The private Pi installation keeps RTSP/GStreamer, camera tracking/control,
vertical geometry and its existing follower gains/authority. Its applied
video-only settings are 720p/15 FPS, 10 FPS startup, JPEG 80–85, an explicit
8,000 kbps budget and disabled preprocessing/blur/CLAHE. The separate inhibited
single-viewer 1080p/4 Mbps demonstration does not overwrite that saved profile.

Native-camera playback avoids our decode/overlay/software-re-encode stage.
That lesson supports preserving source pixels and avoiding unnecessary
preprocessing; it does not establish image-quality parity or justify changing
flight gains. JPEG quality has no effect on H.264/VP8.

## Source and validation

- Backend through `60a118b`: native sender bounds/codec negotiation, actual
  workload diagnostics, explicit retired-setting migration and the canonical
  manual/adaptive workload switch. Public defaults are already committed.
- QGC through `32b633765`: receiver H.264 level negotiation and network evidence.
- Backend combined gates: 649 passed, one optional skipped; the additional
  encrypted Automatic 1 Mbps startup regression passed separately.
- Real encrypted native suite: 42 passed before the additional regression.
- QGC incremental build and changed-file lint passed. Unit/Integration: 470
  passed initially; the remaining Ninja Multi-Config host-path fixture passed
  after correcting PATH. No new Python lint findings against the baseline;
  existing file-wide lint debt remains.
- Actual Pi camera comparison: about 120 seconds per connected window;
  720p/2 Mbps median 14.41 presented FPS, 810p/2 Mbps median 11.60,
  1080p/4 Mbps median 14.40. These are static indoor Linux results.

Private raw evidence/configs: local
`~/.cache/pixeagle-qgc-baseline/native-webrtc-2026-10-19/pi/` and Desktop
`PixEagle-video-test-2026-10-20/`. Do not publish these private directories.

## Publication and remaining gates

Publish the backend feature and QGC integration branches with annotated
qualification checkpoint tags. Keep the stable application version and main
release unchanged; no public QGC PR, public custom-QGC release or platform
Actions dispatch belongs to this checkpoint. Native product advertisement
remains off.

Open: weak-link independent decoded-pixel integrity at forced 1080p/1 Mbps;
representative moving-scene quality and age measurements; multi-client capacity
allocation; browser-provider parity; startup recovery; sustained power/cooling;
and Windows/Android packaged-runtime qualification. Historical Pi undervoltage
flags do not establish their timing or cause. No military/flight/native-camera
parity claim follows from this checkpoint.

Next: complete impaired-link/provenance and concurrent allocation gates, renew
platform tests/builds, then operator acceptance and normal supervised deployment.
Fresh visual checks use the isolated camera-only harness with MAVLink and camera
movement disabled, command preview and circuit breaker enabled. They never
restart the paused field service or restore previous actions.

## Operator camera-bench follow-up

The operator requested field-adjustable parameters and a Camera-engine test,
rather than another local-CSRT-only media demo. The existing replay launcher
now has explicit `--camera-operations` admission, documented in
[Field video tuning](../../../../video/06-configuration/field-video-tuning.md).
It imports the canonical camera provider/installation group and follower name
from the private RTSP profile, preserving command preview, circuit breaker,
MAVLink-off and local-only authentication. It does not import aircraft authority
or field flight gains. There is no new product route or settings store.

Regression gates after this harness change: 133 passed (replay, factory defaults,
API inventory and parameter reload), one existing Starlette deprecation warning;
changed Python Ruff and syntax checks passed, schema remained current. Earlier
649 backend and QGC suite results above precede this harness-only extension.

The new v19/v20 comparison measured approximately 120 seconds per connected
window. At a 15 FPS ceiling, median presentation was 14 FPS, with 107 samples
at 1440×810 and eight at 1080p. At a 20 FPS ceiling, all 115 samples remained
1440×810, median 19 FPS and final 19.2 FPS. Neither sampled window had stale
source or peer errors. v20's guarded runtime peaked at 66.1°C; its separate
ten-second CPU/source sample was 220% of one core and 2.126 Mbps RTSP TCP receive
payload. These measurements do not establish sustained field headroom or
native-camera compression parity. Keep the saved 720p/15 FPS baseline.

The explicit operator bench uses the saved camera engine, vertical mount and
compatible follower identity with that conservative video baseline. Camera
movements are operator actions; no aircraft-control test or stable release is
authorized by successful video presentation alone. Native capability remains
experimental and the open gates above remain.
