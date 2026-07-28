# QGC HTTP/WebSocket Source Plan

This note records the active PixEagle/QGroundControl integration boundary. The
QGC receivers are generic network-video features; PixEagle is one compatible
source, not a special case in QGC.

## Focused QGC Sequence

The former broad draft
[QGC #13594](https://github.com/mavlink/qgroundcontrol/pull/13594) is being
superseded by smaller reviewable changes:

1. [#14727](https://github.com/mavlink/qgroundcontrol/pull/14727) redacts
   credentials, paths, queries, and fragments from stream URL diagnostics.
2. [#14728](https://github.com/mavlink/qgroundcontrol/pull/14728) preserves the
   Windows software-frame rendering path used by JPEG decoders.
3. [#14729](https://github.com/mavlink/qgroundcontrol/pull/14729) fixes an
   independently useful local HTTP test fixture.
4. [#14730](https://github.com/mavlink/qgroundcontrol/pull/14730) proposes an
   unauthenticated HTTP/HTTPS multipart-MJPEG source.
5. [#14731](https://github.com/mavlink/qgroundcontrol/pull/14731) proposes an
   unauthenticated WS/WSS source carrying one complete JPEG per binary message.

The two transport PRs are still proposals until QGC maintainers accept them.
They use strict platform TLS trust, reject URL user information and redirects,
and intentionally do not add Authorization, Origin, custom-CA selection,
credential persistence, or recording-policy changes. Those controls require a
separate generic security design and review.

## Supported PixEagle Paths

| Use case | PixEagle profile | QGC source |
| --- | --- | --- |
| Same computer | `local_only` / `local_compat` | HTTP MJPEG or WebSocket JPEG loopback URL |
| Isolated lab network, anonymous video accepted | `unsafe_demo_lan_media_only` | HTTP MJPEG or WebSocket JPEG device URL |
| Companion-to-GCS field video | `field_qgc_video` | Stock QGC UDP H.264 |
| Authenticated remote native client | `qgc_direct_media` | Future/advanced client with Bearer, Origin, and TLS controls; not supported by #14730/#14731 |

The checked-in default remains authenticated and does not expose anonymous
remote media. For an explicit anonymous media-only lab:

```bash
make unsafe-demo-lan-media-profile LAN_HOST=<pixeagle-device-ip-or-hostname>
```

That profile permits unauthenticated access only to `/video_feed` and
`/ws/video_feed`. It does not make the dashboard, telemetry, configuration,
actions, WebRTC signaling, or media-health APIs anonymous. Restrict selected
GCS devices with a firewall, VPN/overlay ACL, or reverse-proxy source-IP rule;
`API_ALLOWED_HOSTS` validates the request authority and is not a client-IP
allowlist.

For same-host tests, QGC can use:

```text
http://127.0.0.1:5077/video_feed
ws://127.0.0.1:5077/ws/video_feed
```

For the maintained stock-QGC field path:

```bash
make qgc-video-profile GCS_HOST=<gcs-ip>
```

QGC selects **UDP h.264 Video Stream** on the matching port, normally `5600`.
PixEagle's backend remains loopback-only.

## Authenticated Direct Media

`qgc_direct_media` remains a valid PixEagle advanced-client profile:

```bash
make qgc-direct-media-profile PUBLIC_HOST=pixeagle.example
```

It keeps PixEagle behind an external HTTPS/WSS proxy and creates a
`media:read`-only token record plus a one-time plaintext handoff. Omitting
`expires_at` creates a non-expiring token. PixEagle stores only the token hash,
so plaintext cannot be recovered or displayed again. Offline token-file
disable, removal, or rotation currently takes effect after backend restart;
security audit records show individual uses but are not a canonical
`last_used_at` database.

The focused QGC transport PRs cannot consume that Bearer/Origin contract.
Dashboard token management, hot revocation, aggregated last-use metadata, and
generic QGC Authorization/Origin/custom-CA UI remain separate future work.

## Acceptance Boundary

Linux, Windows, and Android integrated receiver tests have exercised both
network-JPEG transports, including the Windows CPU-frame correction. QGC CI,
review, and merge remain authoritative for the focused PRs. PixEagle
Raspberry Pi, PX4/Pixhawk, camera/gimbal, SITL/HIL, field, and aircraft
acceptance are separate gates and are not implied by transport playback.

Use the
[QGC Network JPEG Receiver Test](qgc-windows-receiver-test.md)
for repeatable URL, reconnect, and platform checks.
