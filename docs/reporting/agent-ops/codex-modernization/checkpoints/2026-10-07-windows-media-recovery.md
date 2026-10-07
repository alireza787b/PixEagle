# Windows client media recovery — 7 October 2026

## Scope and operator evidence

This documentation closeout records the operator's Windows tablet report:
latest QGC installed; Windows media features and Visual C++ installed without
reboot; standalone GStreamer installed; video still failed; Windows restarted;
camera available again; video then worked. Physical video recovery is confirmed
by the operator. Tracking, following, restart and interruption recovery are
separate acceptance gates.

The earlier private `pixeagle-qgc-diagnostics-20261007-113226` capture recorded
missing Qt multimedia backends, unavailable QVideoSink and Media Foundation
initialization failure. Its executable matched the private QGC `30c6a1528`
installer. Package inspection found Qt/FFmpeg, Visual C++ and GStreamer runtimes;
both Qt multimedia plugins import Windows Media Foundation DLLs.

Microsoft requires reboot after Media Feature Pack installation even without
a prompt. This makes media-feature activation the leading explanation. The
exact Windows edition/feature and loaded modules after repair are unrecorded;
multiple installations and the camera restart prevent isolating the cause.
No backend setting or default dependency was changed based on this inference.

## Documentation changes and verification

- `docs/video/04-streaming/qgc-windows-receiver-test.md`: Windows media
  prerequisite, explicit reboot, packaged-runtime boundary and diagnostic signs.
- `docs/README.md`: link to that receiver guide.
- This checkpoint preserves the distinction between observed recovery and
  causal inference. The QGC fork contains the matching Windows setup guide.

Changed-file hygiene and relative-link checks passed. The route inventory,
configuration reload and documentation consistency gates passed 105 tests;
schema validation passed without modifying defaults or generated schema.
QGC's changed-file pre-commit gate also passed. Hosted checks are attached to
the documentation PR; documentation checks do not repeat or replace physical
acceptance.

## Remaining qualification

Keep the working tablet installation intact. If failures recur, capture the
Windows edition, Media Foundation startup and exact plugin-loader error before
further repair. No standalone GStreamer installation is added as a universal
QGC client prerequisite. Network/restart qualification and the Pi/router/PX4
ground checkpoint remain separate from this video recovery.
