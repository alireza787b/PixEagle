# PXE-0064 API Exposure Containment Audit

Date: 2026-06-12
Scope: first containment slice for unauthenticated backend/dashboard/media and
MAVLink2REST HTTP exposure.

## Finding

Before this slice, PixEagle still had a high-risk default posture for a
flight-control-adjacent companion application:

- backend startup and docs normalized broad `0.0.0.0:5077` exposure;
- CORS allowed wildcard origins with credentials;
- WebSocket and WebRTC-signaling paths accepted clients before checking
  browser origin;
- launcher output and service helpers advertised LAN URLs;
- dashboard and MAVLink2REST helper defaults were inconsistent with the
  companion local-first policy;
- old local `configs/config.yaml` files could preserve broad exposure without
  any explicit operator decision.

The companion-runtime contract and API modernization plan require PixEagle to
be local-first until real authentication, CSRF, authorization, and legacy
mutation retirement are implemented.

## Decision

Implement a containment foundation now rather than waiting for the full auth
stack:

- default to `local_only`;
- make broad exposure an explicit `trusted_lan_legacy` compatibility mode;
- fail closed for contradictory local-only config;
- coerce old missing-mode broad binds to loopback;
- reject wildcard CORS;
- reject unallowlisted browser origins and DNS-rebinding Host authorities;
- reject WebSocket/WebRTC-signaling Host/Origin mismatches before accepting
  connections;
- align launchers, docs, schema, generated artifacts, and tests in the same
  slice.

`trusted_lan_legacy` is intentionally not described as secure. It is a
temporary compatibility mode for isolated trusted networks only.

## Containment Boundary

Covered by this slice:

- process bind host;
- CORS origin allowlist and allowed request headers;
- HTTP Host authority;
- browser `Origin`;
- browser `Sec-Fetch-Site`;
- video WebSocket Host/Origin;
- WebRTC-signaling WebSocket Host/Origin;
- dashboard dev/prod bind default;
- MAVLink2REST HTTP bind default;
- launcher/service output;
- active operator docs and guardrail tests.

Not covered by this slice:

- user login/session management;
- bearer token issuance/rotation;
- CSRF token lifecycle;
- route-level roles/scopes;
- authenticated media sessions;
- durable security audit log;
- removal of legacy immediate mutation aliases;
- field, SITL, HIL, or PX4 runtime validation.

## Acceptance Evidence

Primary evidence:

- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-12-phase-4-api-exposure-containment.md`
- `docs/apis/api-exposure-boundary.md`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `tests/test_network_exposure_defaults.py`
- `tests/test_docs_infrastructure_consistency.py`

Validation completed:

- 79 focused backend/docs guardrail tests passed.
- Phase 0 gate passed with 60 tests.
- Dashboard test suite passed with 54 tests.
- Dashboard production build passed.
- Schema check passed.
- API candidate inventory regenerated and remains non-callable with zero MCP
  exposure.
- Shell syntax, Python compile, stale-pattern search, and diff hygiene passed.

## Follow-Up Work

Keep PXE-0064 `in_progress` until these remaining slices land:

1. Authenticated browser/operator sessions and machine tokens.
2. CSRF and request-origin policy for browser mutations.
3. Route sensitivity classification and role/scope authorization.
4. Authenticated MJPEG/WebSocket/WebRTC signaling.
5. Security audit events and evidence artifacts for sensitive access.
6. Legacy mutation retirement so dangerous actions use typed guarded resources
   only.

PXE-0066 should then add explicit approved/blocked/deferred dispositions for
generated API/MCP candidates, and PXE-0065 should harden SITL sidecar evidence
acceptance.
