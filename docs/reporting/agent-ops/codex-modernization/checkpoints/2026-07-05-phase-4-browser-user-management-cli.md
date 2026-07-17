# Phase 4 Browser User Management CLI Checkpoint

- Date: 2026-07-05
- Phase: 4
- Issue: PXE-0081
- Slice: offline browser-session user management and break-glass reset
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

PixEagle now has a maintained offline CLI for browser-session user files. This
answers the immediate operational questions:

- where an admin can add/change/remove/disable users;
- how an admin can reset a forgotten browser password;
- how to avoid manually editing PBKDF2 hashes.

This is intentionally offline-first. It does not add a remote web-admin API or
dashboard user-management UI before audit, CSRF, confirmation, and session
revocation semantics are designed.

## Changed Files

- `scripts/setup/manage-browser-users.py`
- `tests/test_manage_browser_users.py`
- `docs/apis/api-security-policy.md`
- `docs/setup/setup-profiles.md`
- `docs/TROUBLESHOOTING.md`
- `docs/INSTALLATION.md`
- `scripts/generate_schema.py`
- `scripts/SCHEMA_COMMENT_CONVENTIONS.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `/home/alireza/PIXEAGLE_BROWSER_USER_MANAGEMENT_CLI_2026-07-05.md`

## CLI

The maintained tool is:

```bash
python3 scripts/setup/manage-browser-users.py --file <API_SESSION_USER_FILE> <command>
```

Supported commands:

- `list`
- `verify`
- `add`
- `set-password`
- `set-role`
- `enable`
- `disable`
- `remove`

Example demo reset:

```bash
python3 scripts/setup/manage-browser-users.py \
  --file configs/secrets/demo-browser-users.json \
  set-password --username pixeagle-demo --generate-password
```

Example production handoff reset:

```bash
python3 scripts/setup/manage-browser-users.py \
  --file "$HOME/.config/pixeagle/secrets/browser-users.json" \
  set-password --username pixeagle-operator --generate-password \
  --credential-handoff-file "$HOME/.config/pixeagle/secrets/reset-handoff.json"
```

## Safety And Security Boundary

- The runtime user file stores only PBKDF2-SHA256 hashes.
- The CLI list output redacts password hashes and plaintext.
- Generated/supplied plaintext can be written to a one-time owner-only handoff
  JSON, but is never written into the runtime user file.
- User-file writes are atomic and owner-only.
- Existing files are backed up owner-only by default.
- The tool refuses symlink writes.
- The tool warns when a change leaves no enabled browser users, so accidental
  lockout is visible during shell maintenance.
- The running auth runtime loads user records at startup. Restart PixEagle, or
  force affected browser sessions to log out, when immediate enforcement
  matters.
- Existing active sessions are not revoked automatically by this offline tool.
- A future dashboard/API user-management surface must be a separate slice with
  admin scope, CSRF, durable audit records, confirmation/idempotency where
  needed, and session revocation semantics.

## Evidence Boundary

This slice changes credential-file maintenance only. It does not claim PX4,
MAVSDK, SITL, HIL, QGC receiver, deployment, follower response, or real-aircraft
success.

## Validation

Focused validation run during implementation:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile scripts/setup/manage-browser-users.py

python3 scripts/setup/manage-browser-users.py --help

PYTHONPATH=src .venv/bin/python -m pytest tests/test_manage_browser_users.py
```

Focused results:

- CLI syntax: passed;
- help smoke: passed;
- user-management tests: 5 passed.

Broader validation run before commit:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_manage_browser_users.py tests/test_setup_profiles.py
PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py
bash scripts/check_schema.sh
PYTHONPATH=src .venv/bin/python -m py_compile scripts/setup/manage-browser-users.py scripts/generate_schema.py
git diff --check
```

Results:

- user-management plus setup-profile tests: 143 passed;
- infrastructure docs tests: 23 passed;
- schema check: passed, schema up to date;
- touched-script syntax: passed;
- whitespace diff check: passed;
- stale unversioned Python script-command scan: no matches in README, docs,
  scripts, or tests.

## Remaining Slices

- PXE-0079: final clean setup walkthrough evidence.
- PXE-0082: OSD/video overlay polish.
- PXE-0083: log evidence bundle UX/import design.
- PXE-0084: typed About/System/update-status.
- PXE-0085: SIH Dev/Training validation surface.
- PXE-0086: safe demo cleanup/rotation and safe update workflow.
