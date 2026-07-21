# Phase 5 Checkpoint: Beginner Lab Credentials And Update Preflight

**Date:** 2026-07-21 UTC
**Slice:** PXE-0120
**Status:** implementation pushed for maintainer retest; remote browser acceptance pending

## Scope

This slice responds to the disposable VPS onboarding failure where a generated
password was awkward to transfer and an active runtime caused the updater to
wait on a lifecycle lock instead of explaining the required stop action.

The fresh Core installation remains loopback-only and creates no dashboard
account. The explicit browser lab path is the beginner-facing remote path.
It remains authenticated, but its Enter default is intentionally admin/admin
for an isolated lab only.

## Changes

- demo_lan_browser and make quick-browser-demo now ask for a dashboard
  username and password in an interactive terminal.
- Pressing Enter keeps the single beginner default admin/admin.
- DEMO_CREDENTIAL_MODE=default selects that credential without prompting.
- DEMO_CREDENTIAL_MODE=generated preserves the one-time random-password path.
- Custom passwords are confirmed interactively; the runtime file stores only a
  PBKDF2-SHA256 hash and the owner-only handoff contains the transfer value.
- Installer summaries and setup docs distinguish fresh local Core from the
  explicit lab profile and warn that the lab default is not production-safe.
- The updater checks for an active runtime before waiting on its outer resource
  lock and prints make stop or pixeagle-service stop instructions. The
  transaction repeats the check under the lock for race protection.

## Validation

- Focused setup/update/installer suite: 203 passed
- Interactive PTY smoke: username prompt, hidden password prompt, two Enter
  responses, hashed credential store, and admin / admin handoff summary
- bash -n for touched shell scripts: passed
- python3 -m py_compile scripts/setup/apply-setup-profile.py: passed
- bash scripts/check_schema.sh: passed (40 sections, 535 parameters)
- git diff --check: passed

No remote/public runtime was changed in this slice. No PX4, QGC, WebRTC,
Raspberry Pi, field, or aircraft claim is made.

## Maintainer Retest

Before updating an active checkout, stop its runtime:

~~~
cd /root/PixEagle
make stop
~~~

Then rerun the one-line installer from the public main instructions. For a
remote browser lab after installation, use the printed quick-demo command and
press Enter at both credential prompts. Use
DEMO_CREDENTIAL_MODE=generated only when a one-time password is preferred.

## Next

Wait for the maintainer's fresh VPS result. If it passes, run the clean Ubuntu
beginner walkthrough and then the exact-tag Raspberry Pi Core-first gate. Keep
production credential/TLS, QGC, PX4/SIH/SITL/HIL, and WebRTC evidence separate.
