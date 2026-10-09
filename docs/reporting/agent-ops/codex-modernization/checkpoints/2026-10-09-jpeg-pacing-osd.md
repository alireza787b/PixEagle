# JPEG pacing and OSD readability checkpoint — 2026-10-09

## Position and evidence

This continues the accepted adaptive-video upgrade. Dashboard WebRTC was smooth,
while Dashboard WebSocket JPEG and QGC JPEG were slow. A read-only authenticated
25-second Pi loopback probe reproduced 7.82 FPS (6.6 FPS in its final ten seconds),
ending at 1280×720/Q85 and roughly 132 KB per frame. The configured aggregate JPEG
budget is 8,000 kbps. The controller reported healthy delivery without accounting
for its own pacing delay; encoding and ACK measurements alone could not expose it.

The probe measures receipt and CPU decoding, not physical camera-to-screen delay
or QGC presentation. It sends no camera or aircraft commands. Existing camera,
mount, follower, safety and deployment configuration remains unchanged.

## Changes

- HTTP and WebSocket completed-delivery feedback includes aggregate-budget wait.
  The existing per-client controller reduces spatial size first under this local
  pressure, tries bounded compression before discarding over half the pixels,
  retains hysteresis, restores cadence before extra detail, and guards
  spatial recovery against an estimated oversize step. Network, encoder and
  renderer feedback remain distinct. Diagnostics expose `budget_wait_ms`.
- OpenCV fast OSD rendering uses resolution-aware font metrics and the same
  top-left layout contract as the other renderer. Small labels have a responsive
  floor controlled by the existing base font scale. Preset offsets scale with
  text, and the text measurement cache is bounded.
- Current OSD guides replace obsolete examples. Adaptive delivery still scales
  baked-in text with the entire image: very low delivery resolutions cannot
  preserve every label. Use the existing minimal preset on narrow links.
- Regression coverage includes paced accepted writes, per-client isolation,
  0.5/1/2/5/10 Mbps budget fixtures, actual font measurements and layout scaling.
  A pre-existing follower-factory integration test now initializes its own
  configuration instead of depending on earlier tests' singleton state.

## Validation

- Backend unit gate: 3,673 passed, two optional GStreamer skips.
- Backend integration gate: 196 passed.
- Combined unit/integration CI-filtered regression: 3,869 passed, two optional
  skips after the follower test's configuration isolation repair.
- Follow-up streaming/OSD regression: 373 passed, two optional skips, including
  bounded compression before large spatial steps and sustainable startup-cadence
  recovery.
- Focused streaming/OSD/API/configuration gate: 457 passed, two optional skips.
- Schema drift check and Python syntax/undefined-name lint passed.
- The generated API inventory was refreshed for changed source hashes.
- Live deployment evidence is retained in the local evidence directory;
  deployment requires the normal stopped-runtime updater.

Evidence: `~/.cache/pixeagle-qgc-baseline/video-2026-10-09/`, including the probe,
baseline samples, unit/integration logs, and identical synthetic OSD fixtures at
480p/720p/1080p. The fast 720p fixture's measured glyph height increased to 18 px.
These fixtures do not establish physical operator acceptance.

The first updated live probe delivered 14.29 FPS over 60 seconds, but reduced
resolution to 320×180. This is a rejected quality tradeoff, not an accepted
profile: the follow-up controller repair tries compression before large spatial
steps and assesses cadence recovery at the client's current rate. Final live
qualification must use that repair.

Pi power interruptions during deployment left 37 empty Git objects and 15
incomplete tracked files. Hash-verified object recovery, tracked-file backups
and restoration passed Git integrity checks; the custom configuration matched
its private backup exactly. Subsequent setup repair remains a deployment gate.
Reboot observations do not establish whether heat, power or operator action was
the cause; later cooled readings were 47–56°C with no current throttling.

## Remaining qualification

Measure the upgraded Pi stream and obtain operator comparison in the existing
QGC installation. No QGC binary change is included. Native authenticated WebRTC
with exact presented-frame association remains a separate open gate; the backend
must not advertise an unqualified interactive native transport. Periodic RTSP
capture reconnection was also observed and recovered; its cause is not resolved
by this pacing repair. Physical failure, presentation and low-link qualification
must retain their existing claim boundaries and camera Stop timing gates.
