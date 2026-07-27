# Phase 5 Checkpoint: Bearer-Token Lifecycle

Date: 2026-07-27
Issue: PXE-0148
Status: local implementation complete; QGC/operator acceptance pending

## Scope

Add one administrator-owned lifecycle for scoped machine credentials without
weakening PixEagle's browser-session boundary or exposing token management to
agents. The ordinary dashboard path creates `media:read` credentials for QGC
and similar video clients.

## Changes

- Added an owner-only bearer-token store with validated hash-only records,
  atomic replacement, backups, immutable runtime snapshots, and idempotent
  revocation.
- Added typed admin-browser-session-only inventory, create, and revoke routes.
  Mutations require CSRF and a durable security-audit event before the token
  file changes.
- Supports 30-day, 90-day, one-year, and explicit lab-only lifetime tokens.
- Returns plaintext once in a no-store response. Later inventory calls expose
  metadata only; dashboard navigation and close remain disabled until the
  operator explicitly dismisses the one-time secret.
- If issuance has an ambiguous response, the dashboard refreshes inventory and
  directs the operator to revoke the newly listed unusable record before retry.
- Shows process-local last-authenticated time without writing the credential
  file for every media request. Active-stream revalidation does not advance the
  timestamp. Backend restart resets this field; security audit remains the
  durable historical record.
- Revalidates active session and bearer principals for MJPEG, video WebSocket,
  and WebRTC signaling, so expiry or revocation terminates existing receipt.
- Browser and production setup profiles configure separate
  `demo-api-tokens.json` and `production-api-tokens.json` stores beside the
  external browser-user file. Browser-demo cleanup removes the lab store; each
  file may remain absent until its first creation.
- Regenerated the API/MCP candidate inventory; all three token routes remain
  non-callable and blocked from tool promotion.

## Validation

- Auth/token/media lifecycle: `145 passed`.
- Setup profiles: `160 passed`.
- API policy, candidate inventory, docs, and parameter reload: `102 passed`
  after
  generated-inventory reconciliation.
- Dashboard: `57` suites, `384` tests, lint, and production build passed.
- Schema check, Python compilation, fatal-Flake8, and `git diff --check`: passed.

## Evidence Boundary

No plaintext token is stored or recoverable after the one-time panel is
dismissed. "Last authenticated" is runtime telemetry, not durable history. This slice
does not prove QGC receipt, TLS/proxy deployment, Raspberry Pi behavior, PX4,
SITL/HIL, field operation, or aircraft safety.

The one-time issuance endpoint deliberately cannot replay plaintext after a
lost response. Dashboard callers use inventory refresh plus explicit revocation
as the compensating workflow; a broader two-phase or durable idempotency
protocol remains a future API design question rather than storing recoverable
credentials.

## Next Gate

On a controlled test deployment, create a token in the dashboard, use it for
QGC HTTP and WebSocket JPEG sources, verify last-authenticated metadata appears, revoke
it, and prove active media receipt terminates. Inspect runtime and security
logs to confirm the token secret is absent.
