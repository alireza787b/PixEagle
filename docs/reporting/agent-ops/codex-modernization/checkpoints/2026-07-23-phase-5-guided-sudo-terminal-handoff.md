# Phase 5 Checkpoint: Guided Sudo Terminal Handoff

Date: 2026-07-23
Status: implementation complete; fresh Ubuntu acceptance pending

## Scope

This slice fixes administrator authentication in the documented interactive
`curl | bash` installer and its guided optional setup paths. It does not change
sudoers policy, store credentials, install a service, run PX4, or establish
Raspberry Pi or field acceptance.

## Root Cause

The bootstrap correctly separated its program pipe from guided answers, but
some child scripts still called raw `sudo -v` or `sudo <command>`. On the
reported Ubuntu terminal, sudo attempted to acquire a password from the wrong
input boundary and failed before `apt` started.

## Implemented

- Added one dependency-free privilege helper in `scripts/lib/common.sh`.
- Root execution remains direct and a valid sudo timestamp remains silent.
- Interactive authentication uses `sudo -S` with the verified stdin terminal
  or `/dev/tty`; PixEagle never reads the password into a shell variable.
- Unattended setup uses only `sudo -n` and fails before a privileged operation
  when authorization is unavailable.
- Required package setup, PyTorch prerequisites, dlib, OpenCV/GStreamer,
  optional service onboarding, and quick-demo firewall operations now share
  the helper.
- Active installation and troubleshooting docs describe the same behavior and
  prohibit passwords in environment variables, arguments, files, or pipes.

## Verification

- Exact pseudo-terminal regression for the piped bootstrap: cached check,
  `sudo -S` validation, and a privileged command passed; the test password was
  absent from the fake sudo argument log.
- No-terminal regression: only nonblocking `sudo -n -v` was attempted and the
  operation returned `authentication_required_noninteractive`.
- Installer UX suite: `43 passed`.
- Related dlib, PyTorch, setup evidence, locking, profiles, and venv suites:
  `264 passed`, `1 skipped`.
- Docs, About/version, API inventory, and parameter reload: `108 passed`.
- Dashboard: `55` suites / `363` tests, ESLint, and production build passed.
- Schema: `38` sections / `513` parameters, no drift.
- Bash syntax, ShellCheck for every migrated script, Python compile, and
  `git diff --check` passed.
- Exact GitHub Actions run `29986007182` passed Windows setup, lint, dashboard,
  unit (`2484 passed`, `42 skipped`), integration (`185 passed`), and full
  coverage (`3523 passed`, `49 skipped`, `1 deselected`) jobs on code commit
  `8158a375`.
- The external Codecov endpoint rejected tokenless ingestion even though the
  pinned action step remained nonblocking and green. PXE-0137 tracks that
  separate CI-service configuration gap; the local XML coverage gate passed.

## Acceptance Boundary

The regression reproduces the input topology and validates the command
contract without using a real password. PXE-0136 remains open until the
maintainer reruns the public one-line installer as a non-root user on fresh
Ubuntu, observes the native sudo prompt, reaches the setup summary, and confirms
that rerunning repairs the partial checkout without deleting operator data.

No Raspberry Pi, Jetson, GStreamer target build, real camera/gimbal, QGC,
PX4/SIH/SITL/HIL, field, or aircraft result follows from this checkpoint.
