# Config Sync

Config Sync reconciles the operator-owned `configs/config.yaml` with checked-in
defaults without treating custom extensions as obsolete.

## Classification

- **New**: a defaults/schema key is missing locally.
- **Changed**: a checked-in default changed since the pre-update baseline.
- **Retired**: an exact local path is listed in
  `configs/config_retirements.yaml` and is absent from active defaults/schema.
- **Unmanaged extension**: a local path is not owned by defaults/schema and is
  not registered for retirement. It is preserved and its value is not returned
  by the sync report.

Absence from defaults or schema is never enough to authorize removal. The
versioned retirement registry is the only removal authority; wildcards and
prefix matches are not supported.

## Dashboard Flow

1. Open **Settings > Config Sync** as an admin.
2. Select new values, changed defaults, or registered retirements. Retirements
   are not preselected. Sensitive defaults are displayed as redacted and are
   resolved from checked-in defaults by the server.
3. Select **Preview**.
4. Review applicable/skipped operations.
5. Select **Apply Previewed**.

Apply requires Config Sync contract v2, explicit confirmation, and the exact
opaque preview token returned in the `plan_digest` field. The token is bound to
the internal plan with a process-local secret; internal source fingerprints are
not returned to clients. Restarting the backend invalidates outstanding preview
tokens. If runtime config, sync metadata, schema, defaults, retirement registry,
or config-audit state changes after preview, the server rejects or rolls back
apply and requires a new preview.

## Persistence And Rollback

- An existing runtime config must be backed up before apply.
- On POSIX, runtime config, metadata, audit, lock, and backup files use `0600`;
  the backup directory uses `0700`. On Windows, PixEagle removes inherited ACLs
  and grants full control only to the current user SID, LocalSystem, and the
  local Administrators recovery group.
- Backup names are collision-safe.
- Cooperating writers are serialized with an in-process lock plus `flock` on
  POSIX or `msvcrt.locking` on Windows. Preview/apply also uses exact-byte
  compare-and-swap digests; advisory locking cannot protect against an external
  process that deliberately ignores the lock.
- Each runtime, metadata, or audit file replacement uses a same-directory
  temporary file, file `fsync`, atomic replace, and directory `fsync` where
  supported. This is per-file atomicity, not a filesystem-wide multi-file
  transaction. The exact write receipt is recorded immediately after atomic
  replacement, before final permission and directory-durability checks, so a
  failure in either post-replace check remains conditionally rollback-owned.
- Before mutation, PixEagle snapshots the exact runtime config, sync metadata,
  config audit, and managed backup inventory. It records the exact post-write
  write receipt only for artifacts the transaction actually changed. A later
  save, strict runtime reload, dependent-manager reload, or audit failure
  restores an owned artifact only while its current fingerprint still matches
  that exact write receipt. Persistence rechecks CAS after preparing the
  temporary payload and immediately before replacement. A detected external
  edit that ignores the advisory lock is preserved; PixEagle reloads the
  resulting disk state and reports that operator recovery is required. No
  portable filesystem API makes the final digest-check/replace pair atomic
  against a writer that deliberately ignores PixEagle's lock. Do not edit
  managed config state directly while PixEagle is running: stop the service or
  use the API/config-sync tooling. When ownership still matches, rollback
  removes transaction-created backups, restores any retention-evicted backups,
  and reloads the prior runtime state.
- Registered retirements are removed from active config. Their values are not
  copied into a hidden archive section; the owner-only full backup is the
  rollback artifact.
- Successful saves require strict `Parameters.reload_config()` cleanup and one
  successful update of both `SafetyManager` and `FollowerConfigManager`, so
  removed attributes or stale dependent config cannot be reported as applied.
- Every config mutation is serialized with follower activation through the
  AppController follower-state barrier. The mutation rechecks active following
  after acquiring that barrier, so a config save cannot race a new follow
  session. If the barrier is unavailable, the write is refused.
- Runtime state is published only after config/metadata persistence and the
  redacted audit record are durable. An audit failure restores persistence and
  the previous runtime generation; it cannot leave an unaudited new generation
  active.
- Runtime publication is one coherent generation. Direct `Parameters` reads,
  compatibility writes, and public manager getters block while publication is
  in progress. Compound consumers use `Parameters.read_generation()` when
  several values must come from the same generation. Failed publication
  restores the prior in-memory generation and does not advance its number.
- Application startup validates and publishes config strictly; missing or
  invalid safety config and unavailable required config consumers stop startup
  instead of silently entering a degraded runtime generation.
- `Safety.GlobalLimits` is a complete, closed contract. Every canonical field
  is required; explicit nulls, coercive strings/booleans, non-finite numbers,
  unknown fields, and contradictory altitude envelopes are rejected before
  publication. Per-follower overrides remain sparse, but supplied override
  values follow the same strict rules and their resolved envelope is validated.
- Config mutations are rejected while following is active.
- Blocking lock, YAML, backup, `fsync`, runtime reload, and model persistence
  work runs on a worker thread so a contended config operation cannot stall the
  ASGI event loop.

## Bootstrap And Updates

Bootstrap and `make sync` never apply config operations automatically.

- Fresh bootstrap initializes the current defaults baseline only when one does
  not already exist, records the exact defaults-file digest and provenance,
  then prints a redacted status.
- Before an existing checkout fast-forwards, the installer or `make sync`
  atomically stages the old `configs/config_default.yaml` as an owner-only local
  file. If staging fails, source files are not changed.
- After update, init consumes that staged file only when no valid baseline
  exists, records its SHA-256 and provenance, and removes the staging file only
  after successful metadata persistence. An existing unresolved baseline is
  never replaced or rewritten; its owner-only permissions are still enforced.
- A missing Python environment or failed post-update metadata reconciliation is
  a degraded setup result with an explicit recovery command, not a successful
  config-ready state.
- Applying new/default-adoption operations advances only those baseline paths.
  Unselected changed defaults remain visible on the next review. Metadata marks
  whether the resulting baseline is full or incremental; a source-file digest
  is retained only when the full baseline exactly represents current defaults.

Manual redacted status:

```bash
.venv/bin/python scripts/setup/config-sync-status.py
.venv/bin/python scripts/setup/config-sync-status.py --json
```

The setup scripts resolve `PIXEAGLE_VENV_DIR`, canonical `.venv`, and legacy
`venv` in that order. Use the interpreter selected by your setup.

After explicitly reviewing every pending changed default, an advanced operator
can acknowledge the current defaults as the new full comparison baseline:

```bash
.venv/bin/python scripts/setup/config-sync-status.py --replace-baseline
```

This command does not change runtime config values, but it clears prior
changed-default comparison history and records explicit-refresh provenance.
Bootstrap and `make sync` never call it.

## API

- `GET /api/config/defaults-sync`: side-effect-free redacted report.
- `POST /api/config/defaults-sync/plan`: dry-run and opaque preview token.
- `POST /api/config/defaults-sync/apply`: operations, `plan_digest`, and
  `confirm: true`.

Plan/apply requests use the strict v2 shape:

```json
{
  "contract_version": 2,
  "operations": [
    {"op_type": "ADD_NEW", "path": ["VideoSource", "VIDEO_FILE_EOF_POLICY"]},
    {"op_type": "REMOVE_RETIRED", "path": ["BOUNDARY_MARGIN_PIXELS"]}
  ]
}
```

Paths contain either one root key or one section and parameter. The old
`section`/`parameter` operation fields and obsolete archive/remove operation
are rejected rather than guessed. Apply adds the opaque `plan_digest` token and
`confirm: true`; preview tokens are invalid after a backend restart.
Reports and plans also return only the canonical `path` array; removed
`section`, `parameter`, `removed_parameters`, and duplicate total/removed count
aliases are not part of contract v2. A retirement `replacement`, when present,
uses the same canonical path-array shape.

Current/default, diff, compare, search, import result, export, sync, and audit
responses recursively redact schema-marked secrets, secret-like paths, URL
userinfo, and secret-bearing URL query parameters. Raw values remain available
only to internal config transactions.

Import `merge` overlays supplied paths on the current local config. Import
`replace` discards prior local extensions but resolves sparse input over the
complete checked-in defaults before validating, so it cannot publish a partial
runtime that silently deletes required subsystems.

These are legacy compatibility routes pending typed `/api/v1/config/*`
promotion. Contract v2 is versioned even on this compatibility route. Admin
`config:write` authorization remains required for plan/apply.
