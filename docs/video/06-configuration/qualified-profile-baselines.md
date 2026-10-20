# Video profile baselines

These are reproducible starting points, not settings that are optimal for every
camera, scene, radio or processor. Configure the existing `VideoSource`,
`Streaming` and `FramePreprocessor` groups through Dashboard configuration.
Review pending restart requirements; updates preserve saved installation values.

The public factory source is `configs/config_default.yaml`. A gitignored
`configs/config.yaml` is an installation override, not a second factory profile.
Use Config Sync preview/apply to adopt defaults or remove retired settings;
loading or updating software does not silently replace saved choices.

| Setting | Factory / no optional GStreamer | Pi vertical-gimbal bench, October 20, 2026 |
|---|---|---|
| Input | Bundled video file | Existing camera RTSP, TCP, 200 ms latency, keepalive/RTCP enabled |
| Capture backend | OpenCV; `USE_GSTREAMER: false` | Existing GStreamer capture runtime |
| Source detail | `NATIVE_CAPTURE_RESOLUTION: true` | Same; camera measured 1920×1080 at about 29.9 decoded FPS |
| Analysis | 640×480 | 640×480; geometry/coordinate convention preserved |
| Delivery | `automatic`, 1280×720 ceiling | `automatic`, 1280×720 ceiling |
| Maximum / startup FPS | 20 / 12 | 15 / 10 |
| Startup spatial scale | 0.75 | 0.75 |
| JPEG quality / maximum | 70 / 85 | 80 / 85 |
| Shared payload allocation | 8,000 kbps | 8,000 kbps |
| Preprocessing / blur / CLAHE | Disabled | Disabled; camera firmware owns tracking |
| Optional UDP output | Disabled | Disabled |
| Tracker / follower | PixEagle CSRT / `mc_velocity_position` | Saved Camera engine / `gm_velocity_vector`; no flight-gain changes |
| Gimbal | Disabled | Existing controls enabled, `VERTICAL` mount |
| Circuit breaker / altitude safeguards | Enabled / enabled | Existing field safety choices are separate; isolated media bench blocks commands |

JPEG quality does not set H.264/VP8 quality. The experimental native WebRTC
provider uses GCC and the shared workload controller. At factory peer-count and
budget settings its per-peer encoder ceiling is 2 Mbps, not 8 Mbps. The browser
aiortc provider is not yet covered by the same payload allocation. Refer to the
[streaming tuning guide](../04-streaming/streaming-optimizer.md#native-encoded-video-tuning)
for actual configurable limits and internal thresholds.

## Other inputs and constrained links

- USB: select `USB_CAMERA` and the appropriate device. Keep the balanced
  delivery/analysis defaults, then measure the negotiated sensor mode. Native
  capture does not invent a new USB mode.
- CSI: use its documented platform runtime and negotiated sensor mode. CSI
  requires its capture dependencies even when ordinary file/OpenCV setup does not.
- RTSP without GStreamer: use the maintained OpenCV input path and measure
  freshness/recovery on the specific camera. Do not assume a successful bundled
  recording qualifies every network camera.
- Constrained links: start with `low_bandwidth` and a payload allocation that
  leaves telemetry/control capacity. It limits spatial scale and cadence; no
  configuration guarantees useful detail below measured link/encoder capacity.
- High-capacity links: retain Automatic until actual presentation, workload and
  cooling permit more detail. Native 1080p/4K and weak-link pixel provenance are
  not qualified by the current 720p evidence. Do not defeat congestion control
  with a high bitrate floor.

## Network and acceptance boundaries

Backend `http://192.168.0.226:5077` is the normal trusted-lab deployment address
in this installation. Tests instead use private loopback port 8197 forwarded to
an isolated backend on the Pi; this does not change the camera's network.
WebRTC ICE chooses the media path separately from the HTTP backend address.

The October 19 Windows bridge was 192.168.0.150/24; Ubuntu's Ethernet test
address was 192.168.0.203/24. A separate NetworkManager profile preserves that
address alongside the laptop's previous Ethernet address and leaves its Wi-Fi
default route intact. Pi is 192.168.0.226/24 and camera 192.168.0.108/24. These
are installation examples, never hardcoded application defaults. Addresses
must be unique and the intended directly connected subnet must have a route.

Read-only source decode, local-tracker media tests, camera-owned tracking and
aircraft following are separate evidence levels. The native capability remains
gated. A short fresh-frame pass or an idle ten-minute run cannot qualify a
sustained connected-viewer workload. Previous 20 FPS camera runs reached the
75°C bench cutoff; 15 FPS is a conservative candidate, not a cooling repair.
Retain cooling and exact-frame provenance gates while evaluating it.

The 15 FPS profile was applied through `ConfigService` with backup, preserving
field geometry, gains and safety choices. The private operator handoff includes
the full resulting config, before-change rollback and receipt. It is not a
public factory profile and must not replace a beginner's default configuration.

## October 20 native 1080p comparison

The same camera, Pi, datalink/Windows bridge and Linux QGC were compared in
command-blocked, camera-control-disabled snapshots. The camera source was
1080p H.264 at about 29.9 decoded FPS; the native sender decoded/re-encoded it
using software x264. JPEG quality does not affect these H.264 results.

| Trial | Configured ceiling | Per-peer encoder ceiling | Actual delivery during the connected window | Median presented FPS | Final encoder-pipeline time |
|---|---|---:|---|---:|---:|
| v15 balanced | 720p / 15 FPS | 2 Mbps | 540p startup, then 720p | 14.41 | 17.63 ms |
| v16 unchanged budget | 1080p / 15 FPS | 2 Mbps | 1440×810 throughout | 11.60 | 18.97 ms |
| v18 extra headroom | 1080p / 15 FPS | 4 Mbps | 1920×1080 throughout | 14.40 | 33.07 ms |

Each health window spans about 120 seconds, with 114–115 samples, no stale
source and no native peer errors. Sampled health cannot exclude every brief
presentation gap. v18 used `WEBRTC_MAX_CONNECTIONS: 1` to obtain a 4 Mbps share
of the unchanged 8 Mbps allocation; this is a single-peer comparison, not a
general recommendation to restrict Dashboard/QGC concurrency. Its connected
30-second CPU sample averaged 210% of one core and peaked at 61.15°C. The full
494.65-second guarded run peaked at 62.8°C and stopped on request; only the
explicit connected window establishes these video results.

The Pi later reported historical undervoltage/throttling bits (`0x50000`),
without active low bits. Their timing/cause is not established. Do not call
this a clean power qualification or infer heat as the cause.

Keep factory 720p/20 FPS and the saved custom 720p/15 FPS profile unchanged.
1080p with adequate measured headroom is a useful optional candidate. A
resolution increase at a fixed bitrate is not automatically a detail increase.
Native-camera RTSP playback avoids this decode/OSD/re-encode stage and is not
equivalent to the current processed QGC path. The 1280-pixel-wide test window
also downsamples 1080p for display. No same-frame image-quality score, aerial
identification range, moving-scene acceptance or native-app quality parity has
been established by the static indoor scene.

Next qualification: paired representative detail/motion scenes, explicit age
and presentation-gap measurements at the settled 1080p state, independent
pixel identity under constrained links, shared allocation with simultaneous
clients, browser parity and clean platform packages. The intermittent 1 Mbps
1080p independent-luminance check remains open; a passing 4 Mbps fixture must
not hide it. Native capability remains gated; 4K is not qualified or enabled
by this comparison. No saved field geometry, gains, flight authority or
installed source revision changed during the 1080p trials.

## Frozen October 20 checkpoint

For the short list of adjustable field parameters, see
[Field video tuning](field-video-tuning.md).

Keep the factory and saved installation values in the first table. The best
measured single-viewer demonstration is an **experimental** override of
`Streaming.STREAM_WIDTH: 1920`, `STREAM_HEIGHT: 1080`, `STREAM_FPS: 15`,
`STREAM_STARTUP_FPS: 10`, `STREAM_MAX_BITRATE_KBPS: 8000` and
`WEBRTC_MAX_CONNECTIONS: 1`, with `ENABLE_ADAPTIVE_QUALITY: true` and
`STREAM_PROFILE: automatic`. The one-peer limit reserves a larger encoder share;
it is not a general multi-client deployment recommendation. Keep the saved
three-client profile intact until concurrent allocation is qualified.

For a deliberate fixed-workload experiment, set the existing
`Streaming.ENABLE_ADAPTIVE_QUALITY` to false through Dashboard configuration and
restart as indicated. It fixes requested dimensions/cadence/JPEG bounds, not
network capacity: WebRTC congestion control and safety/freshness checks remain
active. See the tuning guide for the transport-specific adaptation order and
the browser-provider parity limitation. No additional QGC setup is required.

Qualification tags identify reviewed source checkpoints, not a stable
native-WebRTC release. Ordinary capability advertisement remains gated. Keep
JPEG/browser compatibility, independent frame-provenance checks and existing
installation profiles until the open acceptance gates above are closed.
