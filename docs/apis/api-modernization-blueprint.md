# PixEagle API Modernization Blueprint

PixEagle's current API surface is mixed across `/status`, `/stats`,
`/commands/*`, `/telemetry/*`, `/api/*`, `/api/yolo/*`, `/video_feed`, and
`/ws/*`. Phase 0 freezes that current surface with route inventory tests before
the `/api/v1` migration begins.

## Standards

- New public business routes use `/api/v1/...`.
- Routes use nouns and subresources instead of ad hoc verb collections.
- Multi-step mutations return a tracked command or action resource.
- Mutations that can be retried accept an idempotency key.
- Dangerous actions expose dry-run or preview where practical and require
  explicit confirmation.
- All JSON routes use typed Pydantic request and response models.
- Errors use a structured envelope with machine-readable code, detail,
  timestamp, path, and request ID.
- OpenAPI includes tags, operation IDs, deprecation flags, and safety metadata.
- Compatibility aliases are temporary and tracked in route inventory tests.
- MCP-friendly APIs are not callable MCP tools by default. Generated tool
  candidates are review inventory only until a curated registry, policy
  classification, operator docs, tests/evals, and independent reviewer approval
  promote them into an MCP `tools/list` / `tools/call` surface.
- PixEagle API/MCP does not proxy companion-sidecar mutation APIs. Routing,
  connectivity, sidecar secrets, profile reconciliation, and fleet rollout
  remain outside PixEagle's public contract.
- Agent-specific bypass access to non-PixEagle drone-local HTTP, PX4, MAVSDK,
  MAVLink2REST, or sidecar APIs is prohibited. Agents use the same reviewed
  typed PixEagle API/state contracts as other consumers.

## Initial Canonical Families

```text
/api/v1/system/*
/api/v1/runtime/*
/api/v1/telemetry/*
/api/v1/tracking/*
/api/v1/following/*
/api/v1/flight/*
/api/v1/safety/*
/api/v1/streams/*
/api/v1/models/*
/api/v1/config/*
/api/v1/recordings/*
/api/v1/logs/*
/api/v1/actions/*
/api/v1/commands/*
/ws/v1/*
```

## Route Inventory

Route inventory tests must:

- collect current route registrations without starting Uvicorn, video, MAVLink,
  or PX4 subsystems
- parse both inline `FastAPIHandler` route declarations and the typed
  `/api/v1` route specs in `src/classes/fastapi_api_v1_routes.py`
- resolve typed `/api/v1` path constants from `src/classes/api_v1_paths.py`
  rather than duplicating route strings in the registry
- record `src/classes/api_v1_contracts.py` in generated candidate provenance
  because that module owns the typed `/api/v1` Pydantic contracts and
  error-response metadata
- record `src/classes/api_v1_paths.py` in generated candidate provenance
  because that module owns the typed route paths parsed by the registry
- record `src/classes/api_v1_actions.py` in generated candidate provenance
  because that module owns process-local action resources, idempotency replay,
  guarded action route execution, action resource lookup, and legacy action
  audit behavior for the guarded action candidates
- record `src/classes/api_legacy_control_routes.py` in generated candidate
  provenance because that module owns legacy Offboard start/stop and
  operator-cancel compatibility route bodies; guarded typed action candidates
  still delegate through the start/stop/cancel compatibility bodies until those
  aliases are retired
- record `src/classes/api_v1_read_routes.py` in generated candidate provenance
  because that module owns typed read-route error boundaries for reviewed
  process-local status/telemetry candidates
- record `src/classes/api_v1_snapshots.py` in generated candidate provenance
  because that module owns process-local runtime, following, and tracking
  snapshot semantics for reviewed read-only candidates
- record `src/classes/api_v1_telemetry.py` in generated candidate provenance
  because that module owns typed MAVLink telemetry-health manager delegation and
  fail-closed unavailable fallback semantics for the telemetry health candidate
- record `src/classes/api_v1_sitl.py` in generated candidate provenance
  because that module owns validation-only SITL injection gates, payload
  construction, dry-run summaries, and AppController validation-hook dispatch
  for blocked validation-stimulus candidates
- assert the frozen method/path inventory
- assert there are no duplicate method/path pairs
- explicitly track deprecated aliases until removal

During migration, old routes remain only as compatibility aliases with
deprecation metadata and a planned removal checkpoint.

## Agent And MCP Candidate Inventory

PixEagle keeps generated agent-context artifacts under `docs/agent-context/`.
The current generated candidate inventory is:

- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`

The current docs-stage registry and policy are:

- `docs/agent-context/agent_tools.yaml`
- `docs/agent-context/agent_policy.yaml`

This inventory is non-callable. It is candidate inventory only, not MCP
execution; it is not an MCP registry, not a runtime MCP endpoint, and not
permission for an AI agent or client to execute routes. The generator
classifies the current `/api/v1` routes for reviewer coverage, keeps all
candidates `callable: false`, and marks the initial typed status/telemetry GET
routes as unpromoted read-only candidates only. The docs-stage registry can
record that a candidate has passed review, but it is still not runtime
promotion and not callable MCP exposure.

Action routes, SITL injection routes, config mutation, service control, model
upload, and future flight-adjacent mutations need separate guard design before
they can become callable automation. A GET route can also stay blocked when it
contains sensitive control-resource or audit data.

Future runtime agent/MCP work follows the staged promotion contract:

```text
typed PixEagle route
  -> generated non-callable candidate
  -> curated registry and default-deny policy
  -> typed arguments/results and operator docs
  -> tests, evals, and independent review
  -> authenticated runtime exposure
```

Dangerous actions additionally require proposal/dry-run, explicit confirmation,
idempotency, audit records, cancellation/monitoring, and a final executor
circuit breaker. Documentation/search resources must be allowlisted and exclude
secrets, raw field logs, private network details, and unsafe generated
artifacts. See the
[Companion Runtime Contract](../architecture/companion-runtime-contract.md).

Candidate review completion does not mean promotion. Every candidate must
eventually have an explicit approved, blocked, or deferred disposition;
sensitive GET routes may remain blocked. Future agent evidence/results and
streaming activity events must use versioned typed contracts. Callable MCP,
public web search, assistant streaming UX, and action-enabled agent work remain
deferred until the typed API migration, authentication boundary, and separate
safety review are complete.
