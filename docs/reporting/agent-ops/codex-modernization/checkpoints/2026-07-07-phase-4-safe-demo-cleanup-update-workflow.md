# Phase 4 Checkpoint: Safe Demo Cleanup And Update Workflow

Date: 2026-07-07
Slice: PXE-0086
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

PXE-0086 closes the sharp edges in the beginner browser demo and general update
workflow:

- quick demos now have a confirmation-gated cleanup lane;
- demo cleanup restores local-only config by default;
- firewall cleanup matches the rule shape opened by the quick-demo script;
- update scripts no longer auto-stash, hard-reset, create merge commits, or use
  stale remote refs after fetch failure.

This checkpoint does not claim live firewall deletion, PowerShell execution, a
clean temp-directory release walkthrough, PX4/SITL/HIL success, field success,
or vehicle behavior.

## Files Changed

- `Makefile`
- `README.md`
- `docs/INSTALLATION.md`
- `docs/SERVICE_MANAGEMENT.md`
- `docs/setup/setup-profiles.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-07-05-phase-4-osd-video-overlay-polish.md`
- `install.sh`
- `install.ps1`
- `scripts/lib/sync.sh`
- `scripts/service/cli.sh`
- `scripts/service/sync_and_restart.sh`
- `scripts/setup/quick-browser-demo.sh`
- `scripts/setup/quick-browser-demo-cleanup.sh`
- `tests/test_setup_profiles.py`

## Behavior

`make quick-browser-demo-cleanup` now supports:

- `DRY_RUN=1` no-touch preview;
- `CONFIRM=1` destructive cleanup gate;
- `STOP_DEMO=0` to leave services running during targeted cleanup;
- `REMOVE_DEMO_CREDENTIALS=0` to keep generated demo user files;
- `REMOVE_DEMO_BACKUPS=1` only when backup deletion is intentional;
- `RESTORE_LOCAL_PROFILE=0` only when another reviewed profile is applied next;
- `CLOSE_FIREWALL=1` for UFW cleanup;
- `TRUSTED_CIDR=<cidr>` for scoped LAN/private firewall cleanup;
- `ALLOW_BROAD_FIREWALL_CLEANUP=1` only for intentional broad cleanup outside
  the public-demo path.

Public HTTP demos open broad UFW rules by design when explicitly requested, so
public cleanup deletes broad rules for dashboard/backend ports. LAN/private
cleanup deletes scoped rules only and refuses ambiguous broad deletion by
default.

`make sync`, `pixeagle-service sync`, `install.sh`, and `install.ps1` now:

- refuse dirty worktrees;
- refuse branch mismatch in installer update paths;
- fetch the requested branch explicitly;
- fail on fetch/ref verification errors;
- use `git merge --ff-only`;
- avoid automatic stash, hard reset, and merge commits.

## Validation

Passed:

```bash
bash -n scripts/setup/quick-browser-demo-cleanup.sh scripts/setup/quick-browser-demo.sh scripts/lib/sync.sh scripts/service/sync_and_restart.sh install.sh
```

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_profiles.py tests/test_docs_infrastructure_consistency.py -q
# 167 passed
```

```bash
bash scripts/check_schema.sh
# Schema is up-to-date.
```

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q
# 54 passed
```

```bash
git diff --check
# No whitespace errors. Git reported the existing install.ps1 LF/CRLF warning.
```

Additional smoke:

```bash
make quick-browser-demo-cleanup LAN_HOST=204.168.181.45 DRY_RUN=1 STOP_DEMO=0 REMOVE_DEMO_CREDENTIALS=0 RESTORE_LOCAL_PROFILE=0 CLOSE_FIREWALL=1
```

Confirmed public-demo cleanup dry-run targets broad dashboard/backend UFW rules.

## Review

Initial independent read-only reviewers found:

- cleanup did not restore local-only config;
- `CLOSE_FIREWALL=1` could delete broad LAN/private rules ambiguously;
- public cleanup could miss broad UFW rules opened by public demo setup;
- installers did not check fetch failure before using remote-tracking refs;
- reporting and validation needed to be updated before commit.

Fixes were applied. A replacement DevOps/script-safety reviewer then reported no
blocking issues and confirmed the prior script findings were resolved.

## Residual Risk

- No live UFW deletion was exercised on this host.
- `pwsh` is not installed here, so `install.ps1` was reviewed and covered by
  static contract tests rather than parsed/executed in PowerShell.
- The final clean temp-directory beginner/senior-dev walkthrough remains
  PXE-0074 before release/tag/handoff.
- The current public demo password was not rotated in this slice.

## Next Slice

Proceed to the remaining planned slices, with PXE-0074 final handoff
walkthrough still required before any release/tag/client tester claim.
