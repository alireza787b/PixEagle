# 2026-10-05 — remote dashboard and QGC companion video

## Phase and slice

4b.4d network compatibility repair, after the accepted recorded-video and
camera-v5 checkpoints.

## Change

The production dashboard bundle now runs through a narrow post-build rewrite
for the legacy EdgeHTML parser. Its minifier can emit `condition?.42:.5`,
which EdgeHTML tokenizes as optional chaining and reports as SCRIPT1028. The
rewrite changes only numeric property tokens and adds a cache-busting query to
the generated index so an old 304 response cannot retain the incompatible
bundle. Modern Chrome and current Edge keep their normal bundle semantics.

The QGC custom client now exposes authenticated video and target selection
before PX4 association when the backend advertises unbound tracking. Aircraft
following and PixEagle aircraft-command dispatch remain association-gated.
Backend configuration and supervised restart use the authenticated session;
they are not blocked merely because video or a vehicle is absent. The backend
still advertises the supervisor capability and requires `system:admin`.

## Verification

- `npm run build` completed and `node --check` passed for the rewritten
  dashboard bundle.
- Dashboard API endpoint tests passed (2/2).
- A Chrome login against the Pi dashboard completed with the full dashboard
  rendered and no console errors.
- QGC custom build completed with Qt 6.11.1.
- The focused QGC PixEagle suite passed 8/8, including configuration,
  companion media, target, camera and restart-gating coverage.
- The deployed Pi dashboard archive was SHA-256
  `8f9ef2005a1a663c594865af4e1fdb2867543c7d95924e64cdbb01954a8caeb2`.

## Evidence and limits

The dashboard artifact was deployed to the commissioned Pi and verified from
the Wi-Fi GCS path. The backend's interactive `/docs` route remains local-only
by policy; use an SSH tunnel or a browser on the Pi for OpenAPI inspection.
This checkpoint does not claim physical camera or aircraft qualification.

## Next step

Build the pushed QGC revision on Linux, Windows and Android, then package the
exact artifacts with checksums. The next operator check is Windows Chrome or
current Edge for the dashboard and QGC video before the Pi is powered down.
