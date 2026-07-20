# PXE-0110: Fresh Ubuntu Installer Recovery

## 2026-07-20

- Recovered the interrupted installer slice from the exact fresh Ubuntu 26.04
  transcript. Python 3.14 Core dependencies, one OpenCV contrib provider,
  MAVSDK Server, and MAVLink2REST had succeeded. The actual required-component
  failure was Node/dashboard setup, not the Core Python environment.
- Reproduced the nvm failure. The verified upstream installer rejects a custom
  `NVM_DIR` that does not already exist. PixEagle now creates a private staging
  destination, verifies the downloaded installer SHA-256 and exact nvm commit,
  and publishes `~/.nvm` only after all checks pass.
- Replaced `/dev/tty` node checks with an actual controlling-terminal open
  probe. The one-line bootstrap explicitly chooses Core when no terminal is
  available; direct unattended `make init` requires both noninteractive intent
  and a Core/Full profile. Optional components default to none.
- The isolated Ubuntu rehearsal found and closed one additional defect: under
  `set -e`, the expected nonzero status from stopping an animated spinner could
  terminate setup immediately after nvm staging. Non-terminal runs now print a
  single stable progress line, and spinner cleanup absorbs expected process
  termination statuses. Regression coverage runs cleanup under errexit.
- Moved the Python transaction boundary ahead of Node/dashboard setup. A valid
  Core environment now survives a later Node, npm, or network failure and can
  be reused on `make init` retry.
- Consolidated the runtime on Node.js 24 through `.nvmrc`, package engines,
  setup, dashboard launch checks, and CI. The clean dashboard validation used
  an isolated tracked-file copy so it did not alter the running public demo.
- Added a shared PyTorch/Python compatibility policy. The pinned PyTorch 2.6
  profile accepts Python 3.9-3.13. Full AI on Python 3.14 stops during preflight
  before apt, model-store, or venv mutation; Core can still resolve and verify
  against the host interpreter.
- Made apt package-list refresh and install deterministic, noninteractive, and
  fail-closed. Added clear root-ownership reporting and one final optional menu
  for dlib, OpenCV/GStreamer, a current-user Bash directory shortcut, and the
  separate standalone-service workflow.
- Validation passed: 252 installer/setup policy tests, 72 minimum Phase 0 API
  and reload tests, schema generation check (40 sections / 535 parameters),
  shell syntax and bounded ShellCheck, and a clean dashboard `npm ci`, 53 suites
  / 348 tests, lint, and optimized production build.
- Official Ubuntu `26.04` image digest
  `sha256:3131b4cc82a783df6c9df078f86e01819a13594b865c2cad47bd1bca2b7063bb`
  passed the isolated repaired section with nvm commit
  `977563e97ddc66facf3a8e31c6cff01d236f09bd`, Node `v24.18.0`, and npm
  `11.16.0`.
- The first independent installer review identified explicit unattended intent,
  Python/Full-AI compatibility, deterministic apt, Node-policy drift, service
  readiness, root ownership, and fallback-banner concerns. The release-blocking
  items were closed and regression-tested; fallback banners used only when the
  required shared helper is missing remain minor cleanup debt. A fresh final
  reviewer did not return a verdict within the bounded window and was stopped,
  so no independent final-GO claim is made.

## Next

Publish beta.10 after the exact candidate checks. Then the maintainer should
rerun the complete one-line Core bootstrap on
the fresh Ubuntu host. That external rerun remains the acceptance gate for the
whole installer. Raspberry Pi, Full AI/model, optional GStreamer/dlib target
builds, PX4/SIH/SITL/HIL, QGC, production networking, and field behavior are
separate slices and are not implied by this recovery.
