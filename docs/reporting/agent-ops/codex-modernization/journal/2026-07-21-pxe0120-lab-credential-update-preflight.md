# PXE-0120 Journal: Beginner Lab Credentials And Update Preflight

**Date:** 2026-07-21 UTC

## Finding

The public lab profile generated a random admin password, which was correct
for security but poor for a first-time student/maintainer bench. Re-running
the bootstrap while the manual runtime was active also reached the lifecycle
lock timeout before reporting the stop requirement.

## Decision

Keep the fresh Core default local-only. Make the explicit browser lab path
simple and authenticated: ask for username/password, use admin/admin when the
operator presses Enter, and retain generated credentials as an explicit
optional mode. Do not create a no-password remote dashboard or weaken the
production profile.

## Evidence

- 203 focused setup/update/installer tests passed.
- Interactive PTY smoke accepted two Enter responses and produced a PBKDF2
  user record plus the documented admin / admin lab login.
- Shell syntax, schema, and diff checks passed.

## Resume

The code is pushed to main; the maintainer must stop any active VPS runtime
before rerunning the updater. Public browser acceptance and the fresh Ubuntu
walkthrough remain pending.
