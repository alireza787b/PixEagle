# PXE-0144: Guided Update Recovery

Date: 2026-07-25
Status: implementation and local validation complete; Ubuntu acceptance pending

## Decision

The maintained interactive updater may stop a runtime only after proving that
the manual session or managed service belongs to the current checkout and the
operator accepts one default-yes prompt. It does not restart the runtime.
Unattended stopping is explicit, and ambiguous ownership remains a blocker.

Long maintained setup operations publish a low-rate heartbeat without changing
their transaction or rollback boundaries, and the heartbeat retires if its
parent shell is interrupted. Runtime binary upgrades remain release-controlled
through one checksummed manifest rather than an upstream floating-latest query.

Transactional dashboard environment backups are operator data. New checkouts
ignore `dashboard/backups/`; the public installer can preserve and locally
exclude that exact historical artifact after confirmation. Other worktree
changes remain hard blockers.

## Evidence

- Focused update/setup/reset suite: 120 passed
- Broader installer/lifecycle suite: 348 passed
- Config/docs integration suite: 192 passed
- Required API inventory and parameter reload: 73 passed
- Dashboard lint/build, schema, Bash syntax, ShellCheck, dry-run, and diff
  checks: passed

Fresh Ubuntu one-line update, Raspberry Pi, camera, PX4, field, and aircraft
evidence are outside this local result.
