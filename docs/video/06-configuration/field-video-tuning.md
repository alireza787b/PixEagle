# Field video tuning

Change these existing parameters in Dashboard configuration. Save a known-good
profile, change one setting at a time and honor the pending backend restart.
Video configuration is separate from tracker choice, mounting geometry, follower
gains and aircraft-command authority. Keep those unchanged during video tuning.

## Starting profiles

| Parameter in `Streaming` | Public factory | October 20 private Pi baseline |
| --- | --- | --- |
| `ENABLE_ADAPTIVE_QUALITY` | `true` | `true` |
| `STREAM_PROFILE` | `automatic` | `automatic` |
| `STREAM_WIDTH` / `STREAM_HEIGHT` | `1280` / `720` | `1280` / `720` |
| `STREAM_FPS` | `20` | `15` |
| `STREAM_STARTUP_FPS` | `12` | `10` |
| `STREAM_STARTUP_SCALE` | `0.75` | `0.75` |
| `STREAM_QUALITY` / `MAX_QUALITY` | `70` / `85` | `80` / `85` |
| `STREAM_MAX_BITRATE_KBPS` | `8000` | `8000` |
| `WEBRTC_MAX_CONNECTIONS` | `3` | `3` |

The Pi's lower cadence leaves processing/cooling margin; it is not evidence
that every Pi or datalink has the same limit. Keep native source detail,
640×480 analysis and disabled display preprocessing as documented in the
[profile baselines](qualified-profile-baselines.md). Do not raise analysis
dimensions merely to improve delivered video.

In the fresh October 20 single-peer/4 Mbps comparison, a 15 FPS ceiling gave
14 presented FPS median, mostly 1440×810 with a short 1080p interval. Raising
only the ceiling to 20 gave 19 FPS median at 1440×810. Each sampled window was
about 120 seconds with no stale-source samples or peer errors. A ten-second
sample in the latter run used 220% of one CPU core at 58.95°C. This supports
trying 20 FPS, but does not establish moving-scene quality, extended cooling
or simultaneous-client headroom. Keep 15 FPS as the conservative saved profile.

## Small set of useful controls

| Goal | Change | Watch for |
| --- | --- | --- |
| Smoother motion | Try `STREAM_FPS` 15, then 20 | Actual presented FPS, frame age, temperature and fine-detail loss; more frames share the available bitrate |
| More spatial detail | Try 1280×720, then 1920×1080 ceilings | Actual delivered dimensions, compression artifacts and frame age; a configured ceiling does not force delivery |
| Less link use | Lower `STREAM_MAX_BITRATE_KBPS`; use `low_bandwidth` | Lost fine detail/cadence; retain enough capacity for controls and telemetry |
| Higher JPEG detail | Try `STREAM_QUALITY` 70, then 80, within `MIN_QUALITY`/`MAX_QUALITY` | JPEG encode time and bytes; this does not change H.264/VP8 quality |
| Fixed workload comparison | Set `ENABLE_ADAPTIVE_QUALITY: false` | Requested size/FPS stay fixed, but network congestion control remains mandatory; insufficient capacity can still reduce delivery |

Leave startup scale/cadence and connection limits alone for routine tuning.
`high_quality` still respects resource limits; it does not add link capacity.
Return to the known-good profile if freshness, responsiveness or temperature
worsens. A stationary scene alone does not qualify aerial motion or useful
identification detail. Compare the same scene, viewing size and actual delivery.

## Budget and headroom

`STREAM_MAX_BITRATE_KBPS` is a configured aggregate **payload allowance**, not a
measurement of radio speed. Protocol overhead, MAVLink/control traffic and
other applications need additional capacity. Leave margin below the sustained
goodput measured on the actual moving/obstructed field link; a fast idle ping
or Wi-Fi connection rate cannot establish that margin.

The experimental native provider currently reserves a static share per allowed
peer plus one JPEG share. With an 8,000 kbps allowance and three allowed peers,
each native encoder ceiling is 2 Mbps. With 12,000 it is 3 Mbps; with 16,000 it
reaches the current 4 Mbps per-peer cap. Raise the total allowance only when
the link can support the resulting aggregate load. These are allocation limits,
not promises that congestion control will use or deliver those rates.

The one-peer 1080p/4 Mbps demonstration is a controlled comparison, not a field
fix: lowering the peer count can prevent simultaneous Dashboard/QGC viewing.
The browser aiortc compatibility provider does not yet share this native
allocation/workload contract. Native 4K is not enabled or qualified. See the
[streaming guide](../04-streaming/streaming-optimizer.md) for adaptation order,
diagnostics and remaining provider/platform limitations.

Keep Automatic as the normal setting. Native GCC controls bitrate; the shared
workload controller adjusts cadence and dimensions inside the configured
ceilings. CPU headroom does not prove bandwidth headroom. Current recovery
heuristics may choose smoother 810p over 1080p at the same ceiling; report the
actual result rather than assuming the configured resolution is on screen.

## Camera-engine operator bench

The existing `tools/native_replay_demo.py` launcher accepts an explicit
`--rtsp-config <private-installation-config> --camera-operations` preparation
mode. It imports only canonical camera-provider/geometry settings, the saved
follower name and the existing capture/quality allowlist. It starts the Camera
engine and allows authenticated camera operations. Without this explicit flag,
camera controls remain disabled in the media-only replay.

The snapshot still forces circuit breaker on, command preview, MAVLink off and
an unreachable-as-MAVSDK local server endpoint. It imports neither aircraft
authority nor flight gains and cannot qualify aircraft following. Preparation
does not launch hardware; use the bounded camera bench and inspect its private
manifest before starting. The normal field service stays paused so that there
is one capture/control owner. Changes to the private source profile do not
silently alter an already hashed snapshot.
