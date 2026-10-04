# Native installed Smart models — QGC slice 3b

The authenticated capability `models.operations.v1` exposes the existing model
manager to native clients. It adds installed-model choice and bounded class
labels. It does not download, upload, register, delete, or export models, enable
Smart mode, select a target, start following, or operate a camera.

## Reads

`GET /api/v1/integration/models` requires a browser session or bearer principal
with `models:read`. Local compatibility access is insufficient. The response is
`Cache-Control: no-store`, with `schema_version:1`,
`source:"native_model_inventory"`, `instance_id`, `runtime_id`, and an opaque
SHA-256 `model_generation`. Echo the generation; do not derive it client-side.

The inventory distinguishes `configured_model_id` from `active_model_id`.
`active_model_id` is null while local Smart mode is off. The runtime summary
contains `backend`, effective `device`, `fallback_occurred`, and a concise
`fallback_reason`; it excludes raw backend exceptions and checkpoint paths.

Each of at most 256 `models` entries contains a path-free `model_id`,
`display_name`, `task`, `available`, `unavailable_reason`, `size_mb`, and up to
32 `labels` with `total_labels` and `has_more_labels`. Availability requires
Full AI and previously verified detect/OBB metadata. Core can still read the
inventory and its unavailable reasons. Inventory reads use trust metadata and
never execute or download a checkpoint. A previously registered but uninspected
artifact must be inspected through the existing dashboard/model workflow first.

The inventory-level `available` describes model-manager/AI runtime capability;
it does not guarantee that an installed compatible model exists. Clients use
each entry's `available` and `unavailable_reason` for selection, rather than
inferring compatibility from its name or task alone. The backend rejects an
unavailable entry before loading or persisting a model. No separate native
`smarttracker_supported` flag is needed: verified task support is already part
of entry availability.

`GET /api/v1/integration/models/{model_id}/labels?offset=0&limit=200` returns
`source:"native_model_labels"`, the same identity/generation, and bounded
`{class_id,label}` rows. Offset must be nonnegative and limit must be 1–200.
Missing models return 404. Readers also holding `status:read` and
`telemetry:read` receive `target_state` in the inventory; model-only readers
receive null and gain no target telemetry permissions.

## Selection

`POST /api/v1/actions/model-select` requires `models:read`, `models:select`,
`status:read`, and `telemetry:read`; browser sessions also require CSRF. Supply:

```json
{
  "model_id": "installed-model-id",
  "model_generation": "64-character generation from the current inventory",
  "device": "auto",
  "confirm": true,
  "dry_run": false,
  "idempotency_key": "a new key for this explicit choice",
  "native_context": {
    "guard": { "...": "the complete current target-state guard" },
    "binding_mode": "companion_only"
  }
}
```

The guard and generation above are explanatory placeholders. Use complete
typed objects from the current reads. `device` accepts only `auto` in this
slice; the backend's existing device preference/fallback policy remains the
owner. Model IDs must match `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}` and name a current
inventory entry. Filesystem paths and arbitrary URLs are rejected.

The existing native runtime/vehicle/target guard and companion-only association
rules apply. No frame coordinates are accepted. Following and an active Smart
target block model replacement. The action validates the installed inventory
generation and rechecks it, plus the native guard, after checkpoint validation.
It uses the same dashboard executor, trust checks, persisted configuration, live
runtime rollback, owner event loop, follower lock and tracker/model lock.
Source-observation locks cover short checks only, so checkpoint loading does not
hold video publication or aircraft observation. Target-state reads wait in a
worker thread without blocking the API loop. A model selection is a frame-less
runtime/configuration operation; it does not freeze an aircraft or video source
for the duration of model loading or grant a client lease.

Successful standby selection stays in Classic and returns
`selection_status:"configured"`; a successful live Smart replacement returns
`"active"`. Dashboard and native changes advance the shared target revision.
The response is the existing `APIActionResponse` with `result.model_id`,
`result.selection_status`, `result.model_inventory`, `result.target_state`, and
`result.native_target_revision`, plus the authenticated audit actor.

An executed request returns HTTP 202; dry-run returns 200 without loading or
persisting a checkpoint. Repeating the same key/body/actor returns the original
record with HTTP 200 and `idempotent_replay:true`; changing the body under that
key returns 409. Refresh current state after replay. Failed, interrupted or
unknown outcomes must not be automatically retried with a new key.

Structured errors include `model_generation_stale`, `model_not_advertised`,
`model_unavailable`, `model_target_active`, `native_context_stale`,
`target_revision_stale`, `target_following_active`, and `model_store_busy` (409),
invalid requests (422), missing credentials/scopes (401/403), and unavailable
audit/lifecycle/model execution (503). Raw model paths and load exceptions are
not returned. API/MCP candidates remain blocked, unpromoted and non-callable.

These contracts and mocked tests are not real-model quality, performance,
camera, gimbal, PX4, SITL, or release qualification. Real Full AI replay evidence
is recorded by the paired QGC/runtime checkpoint.
