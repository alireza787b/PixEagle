# Native WebRTC recorded-video and optional-runtime checkpoint

## Position and boundary

This is the native WebRTC software prerequisite slice, following the accepted
field repair. Native QGC production capability remains **disabled** and the
normal QGC build option remains off. No Pi, camera, service, flight gain,
configuration default, credential, public release or GitHub Actions deployment
was changed. aiortc browser WebRTC and authenticated JPEG remain supported.

## Implemented

- A lazy optional GStreamer sender behind the existing authenticated WebRTC
  manager consumes the existing FramePublisher, with no second camera reader.
  Setup/encoding work stays off asyncio. Queues, metadata, teardown ownership,
  stale callbacks and resource capacity are bounded; timed-out native teardown
  continues to reserve its slot until completion.
- Negotiation supports H.264 and VP8. Exact outgoing SSRC/RTP timestamps join
  immutable capture identities/geometry. Original media PTS remain intact.
  Selection frames use the existing retention service, including downscaling.
- A prior client challenge bounds frame age without synchronized host clocks.
  Decoder/presentation joins cannot guess missing/late/cross-epoch identities.
- Corrected TWCC caps negotiation: the first estimator hook had no feedback.
  The repaired five-second loopback observed 43/42 feedback events and 20/11
  bitrate updates for H.264/VP8. Admission now requires the extension in the
  negotiated answer. Feedback availability is not network-envelope acceptance.
- A real QGC receiver presents both codecs through the existing Qt video sink
  and PixEagleVideoItem. Recorded test9 at 1280×720 passes independently decoded
  barcode checks and a displayed-frame selection whose capture ID and retained
  geometry are confirmed by the loopback fixture. This is not a production
  target-action/retarget or visual convergence test.
- Independent read-only QGC capability discovery leaves sign-in/verification
  sequencing intact, binds cookies/Origin to the same endpoint, refuses redirects,
  and discards obsolete replies. Native failures select the JPEG path; the full
  automatic transport/failure matrix remains open.
- Optional dependency installation uses one reconciler from advanced GStreamer
  setup, the OpenCV builder and update/repair of existing GStreamer installations.
  It uses normal resource locking/venv rollback, distro transport/codec packages,
  isolated Python bindings and a pinned Cargo-locked RTP plugin when required.
  Managed plugins are discovered from the active venv under services too.
  Core installs need no GI/GStreamer or new setup choice. Unsupported advanced
  dependencies report degraded capability while retaining working media.

## Files and provenance

Backend: `gstreamer_webrtc_peer.py`, `gstreamer_runtime.py`, frame association,
WebRTC manager/client-config guards, optional setup/check scripts, pinned
`requirements-gstreamer.txt` / `gstreamer-runtime.env`, qualification tools and
corresponding tests. Installation/video guides describe ownership and fallback.

QGC: generic `QGCWebRtcVideoSource`, non-destructive presentation-context meta,
source/receiver integration, independent custom-controller discovery and tests.
See the QGC checkout's `custom-pixeagle/NATIVE-WEBRTC.md`.

Local runtime: GStreamer 1.24.2, Qt 6.11.1; gst-plugins-rs 0.13.7 commit
`cdec77cad2d9b7348d800507bc6eeec5039717eb`, built using Rust 1.75.0 with
`Cargo.lock` preserved. Release QGC SDK remains pinned at 1.28.4. Additional
local development packages were extracted into a user cache, not installed on
hardware. The setup installer was exercised with mocked package/build commands;
its actual Pi package/build path is not yet qualified.

## Verification

- Backend streaming/API/route/configuration and setup gates: **403 passed**.
  Commands include `tests/unit/streaming`, `test_api_v1_streams.py`, route
  inventory, parameter reload, runtime setup and existing CSI setup tests.
- Existing installer/profile/update regressions: **265 passed**.
- Final runtime installer tests after lock/rollback/cache changes: **10 passed**,
  including partial Python install failure and failed plugin verification.
- Without optional GI: **40 passed, 5 skipped**; the skips are real GStreamer
  media/feedback probes. Existing browser aiortc/JPEG capability remains available.
- Schema gate passed. Shell syntax, ShellCheck and focused Python syntax/import
  lint passed. No frontend code changed; Dashboard regression CI remains required
  before release.
- QGC Debug build passed. Standard Unit/Integration selection ran 446 suites:
  445 passed initially, one CMake fixture could not find Ninja. The same fixture
  passed with the project's locked tool directory on PATH. Later focused media
  tests passed after test additions.
- Five consecutive recorded-video QGC runs passed for both H.264 and VP8,
  including exact displayed selection and shutdown/epoch invalidation.
- Changed-file QGC lint passed except existing CMake-format/CMake-lint failures,
  reproduced on pristine HEAD versions. Non-CMake checks pass separately; broad
  reformatting and public helper argument renaming were deliberately not mixed in.

Evidence: `/home/alireza/.cache/pixeagle-qgc-baseline/native-webrtc-2026-10-19/`,
including commands/results, runtime package/plugin checksums, feedback JSON and
QGC presentation/regression logs. Failed intermediate experiments remain separate
from successful final reports; no deployment credentials are included.

## Remaining slices

1. Complete automatic native/JPEG failure/recovery, production selection/action,
   revocation, source changes and lifecycle tests through the custom controller.
2. Measure constrained links, encoder/renderer load, multi-client aggregate
   limits and adaptive FPS/spatial policy. Do not infer available capacity from
   offered video volume. Renew camera Stop/expiry software timing under load.
3. Bundle/probe Windows first, then Linux/Android, including complete WebRTC/ICE/
   DTLS/SRTP/SCTP dependencies. No development GStreamer install on GCS clients.
4. Request a cooled Pi and camera only after software gates pass; deploy through
   the normal updater and preserve the custom profile. Pixhawk is needed later.
5. Retain aiortc as the supported no-GStreamer browser provider. Remove obsolete
   branches only when required compatibility behavior has a qualified replacement.
