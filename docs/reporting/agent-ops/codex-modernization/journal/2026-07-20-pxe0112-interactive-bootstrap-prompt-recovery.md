# PXE-0112: Interactive Bootstrap Prompt Recovery

## 2026-07-20

- Received the complete fresh Ubuntu 24.04 SSH transcript. The bootstrap
  published a verified checkout but the child initializer stopped before
  profile selection with `No controlling terminal is available`.
- Preserved the safety distinction between guided and unattended setup. The
  fix does not assume that a `/dev/tty` path means input is available and does
  not silently approve a direct background `make init`.
- Replaced the two independent terminal decisions with one bootstrap-owned
  input mode. Guided child commands now receive the verified terminal as stdin;
  unattended children retain explicit profile/default behavior.
- Routed both the fresh initializer and existing-checkout updater through that
  command boundary. This matters for the maintainer's next run because the
  failed host already contains a clean checkout.
- Made profile and optional-menu input closure explicit, added yes/no retry,
  and reduced the duplicate bootstrap/initializer banner while preserving the
  established ten-step progress headers and animated long-operation spinners.
- Bumped the coherent runtime/dashboard/setup version to beta.11 and updated
  beginner, installation, troubleshooting, and release documentation.
- Added a real pseudo-terminal regression around an stdin-fed bootstrap. The
  child profile selector accepted Full through the controlling terminal. A
  deterministic prompt test proves invalid yes/no input is retried.
- Validation passed: 317 installer/setup tests with one platform skip, 72
  Phase 0 tests, four version/about tests, schema generation, 348 dashboard
  tests, fresh dashboard install/build, shell syntax/ShellCheck, and exact
  candidate clean handoff 26/26 at
  `aefa882536f21dee9ea55b7e4e018490c21a1ab9`.
- Pushed `main`, published annotated prerelease `v7.0.0-beta.11`, and refreshed
  the public browser-only lab bench without rotating credentials or changing
  configuration. Dashboard HTTP, protected-API rejection, anonymous lab
  MJPEG/WebSocket frames, build identity, runtime ownership, and bounded logs
  passed.

## Next

Ask the maintainer to rerun the unchanged one-line command on the same Ubuntu
host. Do not close PXE-0112 or PXE-0110 until that real run
waits for input and reaches a ready Core summary. Hardware, AI/model,
GStreamer/dlib, PX4/simulation, QGC, production, and field work remain separate
acceptance lanes.

Evidence:

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0112-aefa8825-exact-clean-handoff/manifest.json`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0112-beta11-vps-browser-smoke/manifest.json`
