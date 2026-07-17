# Companion Runtime Reconciliation Audit

Date: 2026-06-11
Slice: Phase 4 PXE-0022
Scope: current MDS, MavlinkAnywhere, and Smart Wi-Fi Manager contracts relevant
to PixEagle API/MCP/runtime modernization.

## Exact References Reviewed

| Repository | Branch state | Reviewed revision |
| --- | --- | --- |
| PixEagle | `codex/modernization-pxe0040-runtime-20260604` | `eafbc63cc6e2a43a96521a31d1c2a4e899648fbf` before this slice |
| MAVSDK Drone Show (MDS) | clean `main...origin/main` | `623bb3fa2cc7e8ab4fe6de032425c1aa17e05186`, `v5.5.71-simurgh-readonly-closure` |
| MavlinkAnywhere | clean `main...origin/main` | `7643d4d9bc75a78fdc6b0f68358c466310ee2c4d`, `v3.0.14-2-g7643d4d` |
| Smart Wi-Fi Manager | clean `main...origin/main` | `a5414fc7d7df1fde47db11aeed1681f5515ea350`, `v2.1.14-2-ga5414fc` |

`git fetch --prune --tags` completed before review. MavlinkAnywhere and Smart
Wi-Fi Manager were unchanged from the 2026-06-05 PixEagle checkpoint. MDS
advanced from `04e53b1f` / `v5.5.64-simurgh-mcp-smoke-heuristic` to the
revision above.

MDS currently selects validated deployment defaults
`MDS_DEFAULT_MAVLINK_ANYWHERE_REF=v3.0.10` and
`MDS_DEFAULT_SMART_WIFI_MANAGER_REF=v2.1.11`, not the newest source repository
commits. This reinforces that deployment pins are compatibility decisions, not
automatic latest-version tracking.

## Reconciled Contracts

### MDS Agent/API Lessons

The MDS changes since the last PixEagle review complete a read-only Simurgh
checkpoint. Relevant durable patterns:

- one typed API/state contract backs dashboard and MCP reads;
- generated OpenAPI candidates are non-callable review inventory;
- registry/policy coverage is an explicit drift gate;
- the canonical MDS environment default disables MCP and requires auth when
  enabled, while specialized reviewed launch profiles can override that
  default;
- action execution remains a separately staged roadmap with dry-run,
  confirmation, monitoring, audit, and a final circuit breaker;
- model-visible context/docs change in the same slice as behavior;
- public docs search uses an allowlisted generated index and excludes secrets,
  raw logs, private details, unsafe generated artifacts, and plans.

PixEagle already follows the typed-route, non-callable candidate, and
docs-stage registry/policy portions. It should not copy MDS's fleet/GCS
implementation or expose sidecar APIs as PixEagle tools.

### Sidecar Security And Profile Lessons

Both reviewed sidecars are local-first single-host runtimes:

- default dashboards bind to loopback;
- remote browser mutations use Basic Auth plus `X-Sidecar-CSRF`;
- remote machine mutations use a sidecar-specific bearer token;
- open-lab bypass is isolated-lab-only;
- fleet-style mutation is dry-run first, then confirmed apply;
- `observe`, `local`, `fleet-merge`, and `fleet-strict` have explicit policy
  meanings;
- redacted summaries/exports are the automation and evidence boundary.

Smart Wi-Fi Manager additionally reinforces secret-file use and recursively
redacted profile exports. It remains optional and external to PixEagle.

## Local Read-Only Probe

Read-only loopback probes were run against the current VPS. No service,
routing, profile, or network mutation was performed.

| Probe | Result |
| --- | --- |
| `GET 127.0.0.1:9070/api/v1/status` | HTTP 200; local installed service reports MavlinkAnywhere `v3.0.8`, zero endpoints |
| `GET 127.0.0.1:9070/api/v1/diagnostics` | HTTP 200; critical `config_parse_failed` because `/etc/mavlink-router/main.conf` is missing |
| `GET 127.0.0.1:9070/api/v1/endpoints` | HTTP 500; config parse failure |
| `GET 127.0.0.1:9070/api/v1/config` | HTTP 500; config parse failure |
| `GET 127.0.0.1:9070/api/v1/profiles/summary` | HTTP 404; route absent in installed `v3.0.8` |
| `GET 127.0.0.1:9070/api/v1/health` | HTTP 200 |
| `GET 127.0.0.1:9080/...` | connection refused; Smart Wi-Fi Manager is not running |

Conclusion: the local MavlinkAnywhere process is alive but old and unprepared.
This is not evidence of usable PixEagle routing, and it is not a current
upstream API contract failure. A future operator-approved runtime preparation
must update/configure the local sidecar before the PixEagle SITL harness can
accept route/profile evidence.

## Decisions

1. Add one canonical PixEagle companion-runtime contract rather than embedding
   sidecar policy independently in API, SITL, and infrastructure docs.
2. Keep PixEagle node-local and sidecar-neutral outside the recommended
   MavlinkAnywhere routing integration.
3. Keep Smart Wi-Fi Manager optional; document its security/profile lessons
   without adding it as a PixEagle dependency.
4. Require exact version/evidence pins per accepted deployment/run, without
   teaching auto-update or treating newest upstream as validated.
5. Keep sidecar mutations outside PixEagle API/MCP. Future agent access uses
   curated PixEagle typed contracts only.
6. Add documentation tests for auth, dry-run/apply, secret, local-first, and
   generated-candidate boundaries.

## Independent Review Findings And Disposition

The API/MCP reviewer confirmed the MDS governance principles worth adopting and
identified patterns PixEagle must not copy blindly:

- prohibit agent-specific bypass access to non-PixEagle
  drone/PX4/MAVSDK/MAVLink2REST/sidecar surfaces;
- treat review completeness as explicit approved/blocked/deferred disposition,
  not pressure to promote every generator-eligible GET route;
- require typed versioned result/evidence/stream-event contracts before any
  equivalent runtime surface;
- keep callable MCP, public web search, assistant streaming UX, drone-log
  tooling, and action-enabled agents deferred.

Those constraints are now explicit in the companion contract, API blueprint,
and agent-context guide.

The security/devops reviewer found two broader runtime debts:

1. PixEagle currently binds an unauthenticated backend broadly and older docs
   normalized LAN/firewall exposure. Active docs were corrected immediately;
   implementation/authentication/legacy-mutation retirement is tracked as
   PXE-0064.
2. The SITL harness does not yet validate installed MavlinkAnywhere dashboard
   version/capabilities, classify preparation failures precisely, or scan
   evidence for secrets. This is tracked as PXE-0065.

The review also found in-slice documentation gaps. They were corrected:

- dry-run plans are process-local and apply must target the same running
  sidecar instance with required acknowledgements;
- Smart Wi-Fi Manager service runtime modes are distinct from reconciliation
  policy modes;
- active update guidance selects a validated tag/commit instead of pulling
  `main`;
- broad unconditional PixEagle firewall rules were removed from active docs;
- remote configuration/troubleshooting guidance now states the current
  unauthenticated boundary;
- the stale Windows/X-Plane procedure was replaced with an explicit
  unmaintained-path disposition instead of remaining an active unsafe guide;
- initial MavlinkAnywhere root install now follows validated revision checkout;
- reviewed companion references are a capability matrix, not automatic
  deployment pins.

PXE-0022 closes the companion contract/reconciliation decision. PXE-0064 and
PXE-0065 remain explicit implementation debt and must close before final
production/no-debt handoff. PXE-0066 owns the new candidate-disposition
governance implementation rather than leaving approved/blocked/deferred as
prose-only policy.

## Claim Boundary

This audit and its docs/tests are contract evidence only. No sidecar was
installed, updated, configured, restarted, or mutated. No accepted
PX4/SITL/HIL/field or real-aircraft result is claimed.
