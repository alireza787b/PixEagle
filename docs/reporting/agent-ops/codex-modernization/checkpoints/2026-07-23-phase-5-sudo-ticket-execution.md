# Phase 5 Checkpoint: Sudo Ticket Execution

**Date:** 2026-07-23  
**Candidate:** `7.0.0-beta.24`

## Scope

The first non-root Ubuntu acceptance run proved that the password prompt was
restored, then exposed a second input-boundary defect: `run_apt_get` replaced
the guided terminal with `/dev/null`. On sudo policies whose credential ticket
is terminal-scoped, the package command could not reuse or renew the ticket.

## Changes

- Kept the guided terminal attached to `apt-get`; package interaction remains
  disabled through `DEBIAN_FRONTEND=noninteractive`.
- Restricted terminal password reads to `pixeagle_sudo_validate`.
- Executed privileged commands with `sudo -n` after validation, preventing
  hidden prompts and accidental consumption of child-process input.
- Extended the pseudo-terminal bootstrap regression through `apt-get update`.
- Updated version, active installation guidance, troubleshooting, and release
  notes.

## Validation

- `PYTHONPATH=src .venv/bin/pytest -q tests/test_init_installer_ux.py`
- Bash syntax and ShellCheck for the changed setup scripts
- Version/docs tests, Phase 0 gates, schema, and diff checks before push

## Evidence And Risk

The focused pseudo-terminal suite passes locally. Real non-root Ubuntu remains
the acceptance gate; the installer rollback already preserved the operator's
previous clean source and ignored runtime data. No Raspberry Pi, PX4, camera,
gimbal, field, or aircraft result is claimed.

## Next

Push the candidate, rerun the documented one-line installer as the normal
Ubuntu user, and close `PXE-0136` only after required packages install and setup
continues beyond Step 2.
