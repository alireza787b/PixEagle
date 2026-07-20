# Phase 5 Checkpoint: Interactive Bootstrap Prompt Recovery

**Date:** 2026-07-20
**Slice:** PXE-0112
**Status:** beta.11 candidate accepted; publication and maintainer rerun pending

## Observed Failure

On a fresh Ubuntu 24.04.4 x86_64 VPS, the documented command
`curl -fsSL .../install.sh | bash` ran in an interactive SSH shell. The
bootstrap accepted the platform, detected enough terminal access to stay in
guided mode, cloned `main` at `8ff630d`, and launched `scripts/init.sh`.
The child initializer then independently reported no controlling terminal and
stopped before asking for Core or Full AI.

No host packages, Python environment, Node installation, binaries, services,
firewall rules, configuration, or runtime were changed after the verified
checkout publication. The failed host therefore remains a clean recovery case.

## Implemented Contract

- The bootstrap now decides its input mode exactly once: `tty` or explicit
  noninteractive.
- In `tty` mode, both the fresh initializer and existing-checkout updater read
  from the already-openable `/dev/tty` instead of inheriting the pipe that
  delivered the bootstrap program.
- In no-terminal mode, the existing explicit Core automation policy remains in
  force. Direct unattended init still requires a declared Core/Full profile.
- Profile and optional-component reads fail visibly if an expected terminal
  closes. Invalid yes/no input is retried rather than silently mapped to the
  default.
- A bootstrap-launched initializer uses one compact setup heading instead of a
  second full ASCII banner. It states the ten-step flow and how Enter accepts a
  displayed default. Existing step headers and animated TTY spinners remain the
  progress authority; non-TTY runs continue to emit stable progress lines.
- The runtime/API/dashboard version is `7.0.0-beta.11` from one tested source
  contract.

## Validation

- Pseudo-terminal regression: installer program delivered through stdin,
  controlling terminal retained, child initializer selected Full successfully.
- Prompt unit regression: invalid yes/no input is rejected and retried.
- Installer/setup/profile/venv/PyTorch/dlib/update suite:
  **317 passed, 1 skipped**.
- Minimum Phase 0 API/reload gate: **72 passed**.
- Version/about contract: **4 passed**.
- Schema: **40 sections / 535 parameters; current**.
- Dashboard: **53 suites / 348 tests**, fresh `npm ci`, and optimized production
  build passed for beta.11.
- Bash syntax, bounded ShellCheck, Python compile, and `git diff --check`
  passed.
- Exact candidate `aefa882536f21dee9ea55b7e4e018490c21a1ab9` passed the
  maintained clean-checkout handoff **26/26** with clean initial/final state.
  The updater dry-run remained intentionally skipped because the public
  browser runtime is active and updater ownership requires a stopped runtime.

## Files Changed

- `install.sh`
- `scripts/init.sh`
- `tests/test_init_installer_ux.py`
- `README.md`, `docs/INSTALLATION.md`, `docs/TROUBLESHOOTING.md`
- `src/classes/app_version.py`
- `dashboard/package.json`, `dashboard/package-lock.json`
- `CHANGELOG.md`

## Remaining Gate

1. Push `main`, tag `v7.0.0-beta.11`, and publish the prerelease.
2. On the supplied Ubuntu 24.04 host, rerun the same one-line command. The
   existing clean checkout must prompt for guarded update consent, then the
   initializer must wait for profile and later choices and complete the Core
   readiness summary.
3. Keep Raspberry Pi, Full AI/model, GStreamer/dlib target builds, PX4,
   SIH/SITL/HIL, QGC, production networking, field, and aircraft validation as
   separate gates.

## Evidence

- Exact candidate clean handoff:
  `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-20-pxe0112-aefa8825-exact-clean-handoff/manifest.json`

## Claim Boundary

This checkpoint proves the scripted pseudo-terminal handoff, prompt behavior,
repository tests, and exact clean-checkout setup contracts. It does not yet
prove completion of the real SSH-host bootstrap that exposed the defect, and it
makes no Raspberry Pi, PX4, simulation, QGC, production, field, or aircraft
claim.
