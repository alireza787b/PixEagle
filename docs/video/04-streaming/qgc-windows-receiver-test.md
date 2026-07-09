# QGC Windows Network Video Receiver Test

This runbook validates a Windows AMD64 QGroundControl build containing the
generic HTTP/HTTPS MJPEG and WebSocket JPEG work from QGC PR #13594. It does
not by itself prove PixEagle deployment, PX4, SITL, HIL, field, or aircraft
behavior.

## Before Testing

- Record the QGC installer SHA-256 and QGC commit.
- Keep PR #13594 in draft until the receiver evidence is accepted.
- Do not put credentials in URLs, query strings, screenshots, or logs.
- Use MKV or MOV for HTTP MJPEG and WebSocket JPEG recording. MP4 is not
  supported for these JPEG sources.
- On Windows, use the session password or session bearer-token field.
  Credential-file loading is a Unix-only QGC option.

QGC is an outbound client. A same-host source needs no inbound Windows firewall
rule. For a source on another host, open only the selected source port on that
source host and restrict it to the test client or trusted test network.

## Lane 1: Generic Anonymous HTTP MJPEG

Use a known test source that serves
`multipart/x-mixed-replace` MJPEG:

1. Open QGC application settings and select **Video**.
2. Select **HTTP MJPEG Video Stream**.
3. Enter the `http://` or `https://` source URL.
4. Under **Network Video Security**, select **None**.
5. Verify first frame, continuous playback, source stop/restart, reconnect,
   malformed URL handling, and source-loss recovery.
6. Record to MKV or MOV, stop recording, and verify the file is non-empty and
   playable.

Anonymous HTTP is a trusted-lab test mode only. It has no confidentiality or
peer authentication.

## Lane 2: Generic Anonymous WebSocket JPEG

Use a server where each binary WebSocket message contains one complete JPEG;
text messages are ignored:

1. Select **WebSocket JPEG Video Stream**.
2. Enter the `ws://` or `wss://` source URL.
3. Select authentication **None**.
4. Verify first frame, continuous playback, disconnect/reconnect, frame-rate
   changes, non-JPEG payload handling, and source-loss recovery.
5. Record to MKV or MOV and verify playback.
6. Test an exact Origin only when the generic source requires one.

Anonymous WS is a trusted-lab test mode only.

## Lane 3: Same-Host PixEagle

When QGC and PixEagle run on the same host with PixEagle's checked-in
`local_only` and `local_compat` policy, use:

```text
http://127.0.0.1:5077/video_feed
ws://127.0.0.1:5077/ws/video_feed
```

Select authentication **None**. Verify QGC and the browser dashboard can consume
video concurrently and that QGC recording does not interrupt PixEagle media.

Docker and WSL can change what `127.0.0.1` reaches. Publish or forward the port
explicitly and record the effective network boundary before accepting evidence.

The temporary public PixEagle browser demo is not this profile. It uses browser
session authentication, which is not QGC's native None/Basic/Bearer video
credential flow.

## Lane 4: Authenticated Remote PixEagle

PixEagle's reviewed remote QGC profile uses a scoped Bearer token, strict TLS,
and a loopback backend behind an HTTPS/WSS reverse proxy. HTTPS MJPEG accepts a
missing native-client Origin but rejects a wrong supplied Origin; WSS requires
the exact generated Origin:

```bash
make qgc-direct-media-profile PUBLIC_HOST=pixeagle.example
```

Use the generated handoff values:

- HTTP MJPEG: generated `https://.../video_feed` URL;
- WebSocket JPEG: generated `wss://.../ws/video_feed` URL;
- authentication: **Bearer token**;
- credential: generated bearer token, entered into QGC's session-only
  credential field;
- Origin: exact generated value for WSS, and optional exact generated value for
  HTTPS MJPEG wrong-Origin rejection checks;
- CA certificate: deployment PEM only when the certificate is not already
  trusted.

Keep PixEagle port `5077` on loopback. Expose only the reviewed TLS proxy port,
normally TCP `443`. Do not expose an anonymous PixEagle backend over LAN or the
public Internet.

Required negative tests:

- missing, wrong, expired, or rotated token;
- HTTP MJPEG accepts a missing Origin from a native client but rejects a wrong
  supplied Origin;
- remote WebSocket JPEG rejects a missing or wrong Origin;
- invalid CA, expired certificate, and hostname/IP SAN mismatch;
- plaintext HTTP/WS with authentication selected;
- reconnect after credential rotation;
- URL, log, screenshot, recording, and evidence-bundle credential redaction.

Basic authentication remains a generic QGC source capability. It is not the
recommended PixEagle machine-client credential model.

QGC does not persist the entered token across application sessions. That does
not shorten the PixEagle machine credential lifetime: the server-side token
remains valid until its configured expiry, disablement, or rotation.

## Evidence Checklist

Capture:

- QGC installer SHA-256, QGC commit, and build-run URL;
- PixEagle commit and sanitized config/profile summary;
- source type and redacted URL;
- QGC logs and screenshots without credentials;
- first-frame and continuous-playback result;
- disconnect/reconnect and negative-test results;
- MKV/MOV recording and playback result;
- TLS certificate/CA summary for secure tests;
- relevant source-host firewall rule;
- test duration and observed memory behavior.

Until these checks pass on the target Windows receiver, do not claim production
PixEagle HTTPS/WSS interoperability, long-duration stability, regression safety
for existing QGC receivers, or PR merge readiness.
