# Config Sync

Config Sync reconciles the operator-owned `configs/config.yaml` with checked-in
defaults without treating custom extensions as obsolete.

## Classification

- **New**: a checked-in default leaf is missing locally. Schema-only sparse
  overrides may be added with an explicit value; they have no invented default.
- **Changed**: a checked-in default changed since the pre-update baseline.
- **Retired**: an exact local path is listed in
  `configs/config_retirements.yaml` and is absent from active defaults/schema.
- **Unmanaged extension**: a local path is not owned by defaults/schema and is
  not registered for retirement. It is preserved and its value is not returned
  by the sync report.

Absence from defaults or schema is never enough to authorize removal. The
versioned retirement registry is the only removal authority; wildcards and
prefix matches are not supported.

Reports compare exact mapping leaves. Arrays and empty mappings remain atomic;
changing one nested setting does not replace its customized siblings. An absent
override still inherits; explicit `null`, `false` and `0` remain present values.
Nested secrets inherit their parent's redaction policy.

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

Schema 1.11 adds `GimbalTracker.HOME_AFTER_TRANSITION`, defaulting to true.
It has no effect unless the gimbal provider and camera controls are enabled
and fresh telemetry identifies a tailsitter transition. See
[Camera Home after a tailsitter transition](trackers/02-reference/gimbal-tracker.md#camera-home-after-a-tailsitter-transition).

`Safety.ALLOW_SESSION_VELOCITY_OVERRIDE` has no runtime reader or supported
schema contract. Its exact path is now registered for removal. Config Sync
shows it for explicit preview/apply; unrelated saves do not silently delete
it. Supported temporary speed controls are advertised by the active follower,
not enabled by this obsolete flag.

Bootstrap and `make update` never apply config adoption/retirement operations
automatically.

Streaming's unused bandwidth/CPU thresholds, cache TTL and `QUALITY_STEP`
are registered retirements. Config Sync offers their exact-path removal;
active payload allocation, cache size and `QUALITY_STEP_ADAPTIVE` values are
preserved. The old values are not translated because their semantics differ.

The unused GM Chase `REQUIRED_TRACKER_FIELDS`, `SAFETY_RETURN_SPEED` and
`DEFAULT_THRUST` settings are also registered retirements. Required observations
come from the command profile, protections from the shared safety envelope, and
GM Chase publishes velocity rather than thrust. Cleanup removes only the selected
exact keys; it does not change gains or apply a new flight policy.

The MC behavior repair changes the fresh rate-profile altitude offset to zero.
Saved offsets are preserved; the resolved shared altitude-guidance flag now
controls whether they are applied. With it off, rate-mode altitude hold captures
engagement altitude. Visual Centering and adaptive Chase also respect that flag;
Ground descent requires it in addition to selecting the descent behavior.
Ground's swapped forward/lateral PID lookup is corrected. Review unequal custom
axis gains before a new acceptance test; factory gains remain numerically equal.

The QGC 4b.4 closeout adds `TargetContinuity.FollowerOverrides` for both gimbal
followers and changes the fresh Vector lateral-mode default to coordinated turn.
An existing flat continuity policy and an explicit saved sideslip choice remain
unchanged. Review the new recovery values in Config Sync and apply them only
while following is inactive; neither QGC nor runtime loading silently adopts
them. Recovery permits bounded horizontal motion after target loss, so adoption
is an operational configuration change, not just a UI update.

The native FW/VTOL extension adds sparse `TargetContinuity.PhaseOverrides`.
Its fresh FW policy retains feasible course/airspeed for up to eight seconds;
the MC four-metre travel budget does not apply. Saved flat/follower policies
remain unchanged until Config Sync adoption. This setting cannot enable an
unqualified native publisher or firmware extension. See the
[native development checkpoint](../native/README.md) before using FW/VTOL.

- Existing runtime config and dashboard environment are preserved together by
  default. Guided setup offers one explicit reset choice only when local
  settings exist; unattended automation uses
  `PIXEAGLE_LOCAL_SETTINGS_ACTION=preserve|reset`.
- An explicit reset validates current checked-in defaults before mutation,
  creates owner-only collision-safe backups of both files, replaces both
  atomically, refreshes the full defaults baseline with reset provenance, and
  appends a config audit record. Any failure rolls back config, dashboard
  environment, sync metadata, audit state, and newly created backups.
- Reset does not remove credentials, models, recordings, logs, or evidence.
  It is separate from Config Sync adoption/retirement and from reinstall.
- Fresh bootstrap initializes the current defaults baseline only when one does
  not already exist, records the exact defaults-file digest and provenance,
  then prints a redacted status.
- Before an existing checkout fast-forwards, the installer or `make update`
  atomically stages the old `configs/config_default.yaml` as an owner-only local
  file. If staging fails, source files are not changed.
- Source publication and guarded rollback reject a target tree that would
  overwrite an ignored or untracked operator path; the operator must resolve
  that path collision explicitly.
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
- Runtime components overlay their checked-in section defaults onto a sparse
  local config while Config Sync is pending. This keeps newly added optional
  components usable without silently rewriting the operator's config; an
  explicit sync or reset is still required to persist the new values.

This optional-default behavior does not relax required configuration contracts.
An incomplete required object such as `Follower.General` fails strict loading
before Config Sync preview is available. Do not remove required fields to request
inheritance. Recover through a reviewed offline configuration repair or explicit
backed-up reset; startup does not silently merge missing required values. Adding
new required fields needs a separately tested pre-start migration path.

### Running Process After A Source Update

Defaults, schema, and the retirement registry are one definition generation.
A running backend never mixes files from a later `git pull` with its older
in-memory generation. `GET /api/v1/config/runtime-status` instead reports a
structured restart-required source state, and the dashboard explains that the
PixEagle process must restart. After source files are repaired or updated,
restart the same owned manual or managed runtime before reviewing Config Sync.

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
Bootstrap and `make update` never call it.

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

Paths contain one root key, a section and parameter, or declared nested mapping
keys (up to 16 components), for example
`["Follower", "General", "YAW_SMOOTHING", "SMOOTHING_ALPHA"]`.
The canonical schema must permit every component; array indexing and descent
through scalar/null values are rejected. A request cannot contain duplicate or
overlapping parent/child paths. `ADD_NEW` without `value` adopts an actual
checked-in default; explicit `value: null` requests null and must be allowed by
the schema. A schema-only sparse path requires an explicit value;
`ADOPT_DEFAULT` never substitutes an inherited or schema annotation value.
Apply advances only selected baseline leaves, preserving unselected changes.
The old
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

`FixedWingGuidance`, `Follower.AIRFRAME_LAYOUT`,
`Follower.AIRFRAME_PHASE_CONFIRMATION_S` are additive native-guidance
settings. Missing saved values retain normal PX4 limits, native throttle and
automatic layout detection; adoption uses preview/apply while following is
inactive. Their follower-restart tier does not restart an active pursuit.
An experimental configuration never overrides the runtime's firmware-capability
check. See [FW guidance policy](followers/04-configuration/fixed-wing-guidance-policy.md).

Schema 1.9 retires `Follower.VTOL_TRANSITION_TIMEOUT_S`: the first fresh transition
or unexpected settled phase ends following and requires a new Start. Saved
values remain inert and unchanged until the existing Config Sync preview/apply
explicitly removes this exact leaf. There is no replacement setting or mapping
to target-loss budgets. `AIRFRAME_PHASE_CONFIRMATION_S` still controls startup
confirmation under the original acquisition identity. Live VTOL admission remains
closed until transition-preserving release is qualified.

Native FW/VTOL engagement requires an explicit `bounded_flight` FW continuity
policy. A saved legacy policy is not silently upgraded during engagement; use
the existing migration preview/apply to adopt the phase override first.

## Optional mission altitude ceiling

Schema 1.10 permits explicit `Safety.GlobalLimits.MAX_ALTITUDE: null` for no
application ceiling. Numeric saved limits keep their meaning; missing values
still inherit the 120 m factory default. No migration automatically removes a
ceiling. Preview/apply preserves explicit null and the existing floor. Follower
overrides remain finite or omitted; follower null cannot remove a global limit.
See [altitude limit semantics](followers/06-safety/limits-configuration.md#optional-upper-mission-ceiling).
Older backends reject this new value, so restore a numeric ceiling before rolling
back to a schema older than 1.10. Native aircraft performance limits are separate.

## Gimbal guidance migration

Schema 1.8 retires `GimbalTracker.GUIDANCE.CAPABILITIES`. Runtime reads only
`ALLOWED_MANOEUVRES` and `OBSERVATION_LIMITS`; the original object remains in
saved config for review, including after unrelated saves. Known Topotek factory
placeholders preserve accepted MC behaviour. Custom or ambiguous declarations
keep API/startup available but refuse Vector Start until reviewed.

Config Sync reports historical provider masking separately from an unverified
fallback and previews the canonical effective result. For custom migration,
provide explicit `ADD_NEW` values for `ALLOWED_MANOEUVRES` and the complete
`OBSERVATION_LIMITS` object, then `REMOVE_RETIRED` on the exact legacy path in
one preview/apply. Explicit null is different from omitting `value`. If the new
fields already exist, edit them through the normal schema editor before
previewing cleanup. Saved restrictions must be preserved or narrowed; widening
is refused during retirement. The report supplies suggested intersected values.

`ALLOWED_MANOEUVRES: null` retains implemented MC states; `[]` permits only
forward. Each observation-window axis is either null (no added restriction) or
an ordered numeric pair. Neither null nor historical provider full-sphere
metadata establishes mechanical reach, camera aim authority, physical target
identity or exposure timing. No physical FW qualification is added by migration.
See [gimbal guidance](followers/04-configuration/gimbal-guidance.md) for examples.
