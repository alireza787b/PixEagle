# Phase 5 Checkpoint: Visible Privilege Renewal

**Date:** 2026-07-23  
**Candidate:** `7.0.0-beta.25`

## Finding

Ubuntu update/repair and sudo package installation succeeded. Browser-lab
startup then appeared frozen after credential creation because the UFW status
pipeline suppressed stderr while an expired sudo ticket requested renewal.

## Changes

- UFW setup and cleanup now announce status inspection, preserve the native
  sudo prompt, and leave rules unchanged if inspection fails.
- Optional service-state and OpenCV temporary-swap privilege calls no longer
  suppress a possible renewed authentication prompt.
- A repository regression rejects hidden stderr around privileged helpers in
  every maintained guided setup script.

## Validation

- Installer and setup-profile tests: `202 passed`
- Phase 0, schema, Bash syntax, ShellCheck, version/docs, and diff gates before
  push

## Boundary

The diagnosis is grounded in the exact output location and owned script path.
The second Ubuntu browser-lab rerun remains the acceptance gate. No Raspberry
Pi, PX4, camera, gimbal, field, or aircraft result is claimed.
