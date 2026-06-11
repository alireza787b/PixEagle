# Companion Runtime Contract

PixEagle is a node-local vision, following, and flight-control-adjacent
application. It can consume services provided by companion-sidecar projects,
but it does not own their configuration, secrets, service lifecycle, or fleet
rollout.

This document is the source of truth for that ownership boundary.

## Responsibility Matrix

| Component | Owns | Does not own |
| --- | --- | --- |
| PixEagle | vision/tracking, follower intent, guarded Offboard actions, typed PixEagle API, local operator UI | MAVLink routing policy, Wi-Fi policy, sidecar upgrades, fleet rollout |
| MavlinkAnywhere | `mavlink-router`, endpoint policy, router dashboard/API, router service lifecycle | PixEagle actions, follower safety, MAVLink2REST, fleet orchestration |
| MAVLink2REST | local MAVLink telemetry HTTP bridge | routing, Offboard commands, sidecar policy |
| Smart Wi-Fi Manager | optional node-local NetworkManager profile policy and connectivity status | PixEagle runtime, MAVLink routing, fleet orchestration |
| External fleet/orchestration system | version selection, non-secret baseline distribution, staged reconciliation, evidence collection | bypassing node-local safety or sidecar confirmation gates |

MavlinkAnywhere is the recommended routing sidecar. Smart Wi-Fi Manager is
optional and is not a PixEagle runtime dependency. A deployment may use another
connectivity manager or no connectivity sidecar.

## Local-First Exposure

Keep management and telemetry sidecars on loopback by default:

| Service | Default |
| --- | --- |
| MavlinkAnywhere dashboard/API | `127.0.0.1:9070` |
| Smart Wi-Fi Manager dashboard/API | `127.0.0.1:9080` |
| MAVLink2REST HTTP API | `127.0.0.1:8088` |

Loopback access inherits the host/SSH trust boundary. Non-loopback exposure
requires an explicit deployment decision, firewall or VPN restriction, and the
sidecar's supported authentication controls.

Remote browser mutations use sidecar dashboard Basic Auth plus
`X-Sidecar-CSRF`. Remote machine mutations use bearer tokens:

- `MAVLINK_ANYWHERE_API_TOKEN` for MavlinkAnywhere;
- `SMART_WIFI_MANAGER_API_TOKEN` for Smart Wi-Fi Manager.

Do not place tokens, passwords, private keys, or real Wi-Fi credentials in
PixEagle config, source control, docs, fixtures, reports, command-line
arguments, or MCP client files. Prefer restricted secret files and
`password_file` for durable Smart Wi-Fi Manager credentials.

Open-lab modes deliberately weaken remote mutation protection. They are valid
only on isolated disposable lab networks and are not an accepted field,
production, CI, or shared-VPS configuration.

## Profile Reconciliation

Sidecar profile reconciliation is external to PixEagle. The safe automation
contract is:

1. read redacted status/summary;
2. validate and diff a non-secret candidate baseline;
3. import with `dry_run=true`;
4. review the resulting plan, warnings, and confirmation token;
5. apply the stored dry-run plan on the same running sidecar instance with
   explicit confirmation and `acknowledged_risks`; include the additional
   strict-policy acknowledgement when required;
6. capture redacted result and rollback/evidence metadata.

Dry-run plans and confirmation tokens are process-local and can be lost when a
sidecar restarts. Never assume that a plan created by one process instance can
be applied by another.

Supported policy meanings:

| Mode | Contract |
| --- | --- |
| `observe` | report only; reject apply |
| `local` | node-local configuration remains authoritative; reject fleet apply |
| `fleet-merge` | apply the baseline while preserving permitted local additions |
| `fleet-strict` | authoritative/pruning policy; advanced use only with additional confirmation |

For MavlinkAnywhere, even strict reconciliation preserves the node-local
hardware input overlay. For Smart Wi-Fi Manager, prefer `fleet-merge` so a
field/emergency access profile is not removed accidentally. A remote network
change can sever the management path; it requires a separate rollout and
recovery plan.

Smart Wi-Fi Manager's service runtime modes (`manage`, `observe`, `disabled`)
are separate from profile reconciliation modes (`observe`, `local`,
`fleet-merge`, `fleet-strict`). Do not use one as evidence of the other. An
omitted reconciliation mode can also have a sidecar-specific default; automation
must send the intended mode explicitly.

## Version And Evidence Policy

PixEagle does not silently clone, update, or install companion repositories.
Each deployment and accepted SITL/field evidence bundle must record:

- exact companion repository URL and commit/tag;
- container image tag and digest where applicable;
- effective redacted sidecar config/profile summary;
- management bind/auth mode;
- exact probe commands and results.

The latest upstream commit is not automatically the validated deployment
version. Version selection and upgrades require compatibility review and staged
validation. Historical audit pins belong in modernization audit/checkpoint
reports, not as unqualified permanent defaults in active operator docs.

Reviewed capability references for this contract:

| Project | Reviewed source | Compatible capabilities required by PixEagle evidence |
| --- | --- | --- |
| MavlinkAnywhere | `7643d4d9bc75a78fdc6b0f68358c466310ee2c4d` (`v3.0.14-2-g7643d4d`) | typed status/diagnostics/endpoints/config/profile-summary reads; guarded dry-run/apply profile flow |
| Smart Wi-Fi Manager | `a5414fc7d7df1fde47db11aeed1681f5515ea350` (`v2.1.14-2-ga5414fc`) | local-first auth, redacted profiles, guarded dry-run/apply flow; optional only |
| MDS reference | `623bb3fa2cc7e8ab4fe6de032425c1aa17e05186` (`v5.5.71-simurgh-readonly-closure`) | agent/API governance reference only; not a PixEagle runtime dependency |

These are review references, not automatic deployment pins. An accepted
deployment/run records and validates its own selected versions.

Read-only health or status success is not routing success. MavlinkAnywhere is
prepared for PixEagle only when the required endpoint, config, and profile
summary probes succeed and the required enabled normal-mode outputs are
present. A running service with a missing router config remains unprepared.

## API, Agent, And MCP Boundary

PixEagle's typed `/api/v1` contracts are the only future source for PixEagle
agent/MCP capabilities. Sidecar APIs remain separate operational surfaces.
PixEagle must not proxy their mutation APIs into a broad agent tool.
Agent-specific bypass access to non-PixEagle drone-local HTTP, PX4, MAVSDK,
MAVLink2REST, MavlinkAnywhere, Smart Wi-Fi Manager, or other sidecars is
prohibited. Agent reads must use the same reviewed typed PixEagle API/state
contracts as all other consumers.

Generated OpenAPI candidates are non-callable review inventory, not a runtime
permission grant. Promotion requires a curated registry, default-deny policy,
typed arguments/results, safety notes, tests/evals, operator approval, and
independent review. Action-capable tools additionally require dry-run,
confirmation, idempotency, audit records, cancellation/monitoring, and a final
executor circuit breaker.

Review completeness means every candidate has an explicit approved, blocked, or
deferred disposition. It never requires promotion. A sensitive GET can remain
blocked indefinitely even when every candidate has been reviewed.

The MDS pattern is a useful reference, not a dependency or implementation to
copy blindly. In particular:

- MDS's canonical environment default keeps MCP disabled
  (`MDS_MCP_ENABLED=false` in the reviewed reference), although specialized
  reviewed launch profiles can override it;
- generated route candidates never become callable automatically;
- docs/context are product inputs and must change with behavior;
- public-doc search must exclude secrets, raw logs, private network details,
  and unsafe generated artifacts;
- real/SITL mode, operator approval, and final execution policy remain
  independent gates.

Callable MCP runtime, public web search, assistant streaming UX, drone-log
tools, and action-enabled agents remain deferred until the typed API migration,
authentication boundary, and separate safety review are complete. If streaming
agent events are added later, their evidence and result payloads must be
versioned typed contracts rather than ad hoc dictionaries.

## Validation Boundary

PixEagle tests may perform read-only loopback sidecar probes. They must not
install services, change routing, apply profiles, restart sidecars, or alter
network connectivity without explicit operator approval.

An accepted integration result requires the evidence contract defined in
[SITL Setup](../drone-interface/04-infrastructure/sitl-setup.md). Sidecar
contract review alone is documentation/contract evidence, not PX4/SITL/HIL or
real-aircraft validation.
