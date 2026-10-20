# Video profile baselines

These are reproducible starting points, not settings that are optimal for every
camera, scene, radio or processor. Configure the existing `VideoSource`,
`Streaming` and `FramePreprocessor` groups through Dashboard configuration.
Review pending restart requirements; updates preserve saved installation values.

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
