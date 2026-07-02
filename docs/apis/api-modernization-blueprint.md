# PixEagle API Modernization Blueprint

PixEagle's current API surface is mixed across `/status`, `/stats`,
`/commands/*`, `/telemetry/*`, `/api/*`, `/api/yolo/*`, `/video_feed`, and
`/ws/*`. Phase 0 freezes that current surface with route inventory tests before
the `/api/v1` migration begins.

## Standards

- The checked-in backend exposure posture is local-only. Non-loopback bind/CORS
  exposure requires explicit `trusted_lan_legacy` configuration plus scoped API
  authorization. Browser-session auth exists for reviewed deployments, but
  production remote-browser setup should use the guarded `production_remote`
  profile or an equivalent reviewed HTTPS/WSS config and still requires
  proxy/firewall evidence, credential handoff evidence, adversarial auth/media
  tests, and safety evidence before handoff. See the
  [API exposure boundary](api-exposure-boundary.md).
- Every HTTP, media, WebSocket, documentation, and validation route must have
  exactly one declarative security classification. Missing or ambiguous
  classifications fail closed. See the
  [API security policy](api-security-policy.md).
- Browser sessions use role-derived scopes plus session-bound CSRF for
  mutations. Machine credentials use named, hashed, revocable bearer tokens
  with exact scopes and no query-string token transport.
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
  provenance because that module owns internal Offboard start/stop and
  operator-cancel compatibility executors used by guarded typed action
  candidates after the former `/commands/*` HTTP aliases were retired
- assert that `src/classes/api_legacy_config_sync.py` owns legacy
  `/api/config/defaults-sync*` report and dry-run plan helper logic so defaults
  migration semantics do not drift back into the handler monolith, and record
  that helper in generated candidate provenance because it owns request-model
  and planning semantics used by legacy config routes
- assert that `src/classes/api_legacy_config_routes.py` owns legacy config
  read/mutation/apply route bodies for schema/current/default reads,
  section/category listing, diff/compare, defaults-sync read/plan/apply,
  backup history, export/import, search, audit, parameter/section updates,
  validation, revert, and backup restore, and record that helper in generated
  candidate provenance because it owns legacy response shaping, query parsing,
  rate-limit handling, save/reload orchestration, and rollback semantics before
  typed `/api/v1/config/*` promotion
- assert that `src/classes/api_legacy_model_routes.py` owns legacy
  `/api/models/*` and deprecated `/api/yolo/*` model route bodies, and record
  that helper in generated candidate provenance because it owns model-list,
  active-model, label, upload, download, switch, delete, and file-download
  semantics used by model management routes
- assert that `src/classes/api_legacy_recording_routes.py` owns legacy
  recording and storage route bodies for start/pause/resume/stop/status/toggle,
  listing, file download with Range support, delete, storage status, and
  include-OSD toggling, and record that helper in generated candidate
  provenance because it owns legacy response shaping, file response headers,
  source dimension probing, and delete/error mapping before typed
  `/api/v1/recordings/*` promotion
- assert that `src/classes/api_legacy_gstreamer_routes.py` owns legacy
  GStreamer route bodies for status and runtime toggle, and record that helper
  in generated candidate provenance because it owns legacy process-local
  writer detection, QGC UDP/RTP setup hints, handler creation, direct config
  flag mutation, and failed-open response mapping before typed
  `/api/v1/streams/gstreamer*` promotion
- assert that `src/classes/api_legacy_media_routes.py` owns legacy bounded
  media observability route bodies for streaming status, streaming stats, and
  video health, the legacy HTTP MJPEG body for `GET /video_feed`, the legacy
  video WebSocket route body for `WS /ws/video_feed`, plus the legacy live
  recovery mutation body for `POST /api/video/reconnect`, and record that helper
  in generated candidate provenance because it owns legacy response shaping for
  transport counts, quality-engine state, OSD pipeline stats, video connection
  health, OBB pipeline diagnostics, MJPEG session-bound response cleanup,
  WebSocket pre-accept security and task orchestration, and reconnect
  success/503/500 mapping before typed `/api/v1/streams/*` replacement or
  compatibility retirement.
- assert that `src/classes/webrtc_manager.py` owns the legacy WebRTC signaling
  state machine for `WS /ws/webrtc_signaling`, and record that manager in
  generated candidate provenance because it owns pre-accept streaming,
  Host/Origin, authorization, and security-audit gates, accept-then-capacity
  behavior, server-owned peer IDs, SDP/ICE handling, browser-session revocation,
  bounded peer cleanup, and shutdown cleanup before any typed
  `/api/v1/streams/*` replacement or compatibility retirement.
- assert that `src/classes/api_legacy_osd_routes.py` owns legacy OSD route
  bodies for status, toggle, preset listing/loading, color-mode switching, and
  mode status, and record that helper in generated candidate provenance because
  it owns legacy response shaping, preset-file validation, cache invalidation,
  renderer reinitialization, and existing legacy error mappings before typed
  `/api/v1/osd/*` promotion
- assert that `src/classes/api_legacy_follower_routes.py` owns legacy follower
  route bodies for schema, profile list, current profile, profile switching,
  health, restart, configured mode, setpoints status, current mode, and config
  manager reads, and record that helper in generated candidate provenance because
  it owns legacy follower response shaping, profile validation,
  active-versus-configured follower handling, health/resource cleanup
  diagnostics, restart rate-limit and reload behavior, setpoint-status
  compatibility fields, safety-limit summary lookup, and config-manager response
  shaping before typed `/api/v1/following/*` or `/api/v1/follower/*` promotion
- assert that `src/classes/api_legacy_safety_routes.py` owns legacy safety,
  circuit-breaker, and safety/config route bodies for circuit-breaker
  status/statistics, circuit-breaker toggle, safety-bypass toggle, statistics
  reset, safety config, follower safety limits, effective limit summaries, and
  relevant-section lookup, and record that helper in generated candidate
  provenance because it owns legacy response shaping, SafetyManager fallback
  behavior, circuit-breaker diagnostics and process-local `Parameters`
  mutations, rate-unit conversion, section relevance mapping, and legacy error
  wrapping before typed `/api/v1/safety/*` promotion. The circuit-breaker
  mutation routes remain legacy, non-idempotent compatibility actions and still
  need typed `/api/v1` action/deprecation design.
- assert that `src/classes/api_legacy_tracker_routes.py` owns legacy tracker
  selector/config/diagnostic route bodies for available tracker listing,
  hardcoded available-types listing, current tracker details, legacy tracker
  switch compatibility, deprecated set-type compatibility mutation, tracker
  restart, current tracker config, tracker output, capabilities, schema file
  read, and current-status diagnostics, and record that helper in generated
  candidate provenance because it owns schema-manager lookup, runtime-status
  embedding, `AI_AVAILABLE` capability payloads, direct legacy AppController
  state mutation, restart rate-limit/reload behavior, deprecation payloads,
  diagnostic field shaping, raw gimbal/status field surfacing, schema-file
  error wrapping, and legacy error shapes before full typed
  `/api/v1/tracking/*` replacement or compatibility retirement work. New
  clients should use `POST /api/v1/actions/tracker-switch` and
  `POST /api/v1/actions/tracker-restart`; broader tracker configuration
  mutation still needs typed action/deprecation design. Dashboard legacy
  fallback from the typed tracker catalog/current/available/switch surfaces now
  records bounded client-side compatibility fallback events and dispatches the
  `pixeagle:tracker-compatibility-fallback` browser event before the legacy
  request is attempted. The typed tracker catalog now also embeds
  process-local backend compatibility counters for attempted legacy
  `/api/tracker/*` route handling, including deprecated `set-type`; route
  retirement and broader typed tracker configuration mutation remain separate
  work.
- record `src/classes/api_v1_read_routes.py` in generated candidate provenance
  because that module owns typed read-route error boundaries for reviewed
  process-local status/telemetry/media-health candidates
- record `src/classes/api_v1_snapshots.py` in generated candidate provenance
  because that module owns process-local runtime, following, tracking
  runtime/telemetry, and typed tracker catalog snapshot semantics. The typed
  tracker catalog route is generated as non-callable and blocked until a
  separate output-sensitivity/policy review promotes it.
- record `src/classes/api_v1_telemetry.py` in generated candidate provenance
  because that module owns typed MAVLink telemetry-health manager delegation and
  fail-closed unavailable fallback semantics for the telemetry health candidate
- record `src/classes/api_v1_streams.py` in generated candidate provenance
  because that module owns typed media transport and frame-publisher health
  snapshots for the streams media-health candidate
- record `src/classes/api_v1_sitl.py` in generated candidate provenance
  because that module owns validation-only SITL injection gates, payload
  construction, dry-run summaries, and AppController validation-hook dispatch
  for blocked validation-stimulus candidates
- record `src/classes/api_exposure_policy.py`,
  `src/classes/api_auth_runtime.py`, `src/classes/api_security_audit.py`,
  `src/classes/api_security_types.py`, and
  `src/classes/api_security_policy.py` in generated candidate provenance
  because they own exposure-boundary decisions, runtime auth decisions,
  durable security audit events, principal/scope semantics, and the
  default-deny route classification reviewed before any future runtime API/MCP
  promotion
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
candidates `callable: false`, and marks the initial typed status/telemetry/media-health
GET routes as unpromoted read-only candidates only. The docs-stage registry can
record that a candidate has passed review, but it is still not runtime
promotion and not callable MCP exposure.

Every generated candidate must carry an explicit `review_disposition`:

- `approved_for_review_only`: accepted as a docs-stage candidate only, still
  excluded from runtime MCP exposure.
- `blocked`: not eligible for agent/MCP promotion without a separate design,
  tests, policy update, and independent review.
- `deferred`: intentionally postponed to a later validation/safety slice; still
  non-callable and unpromoted.

The disposition must include an owner, rationale, evidence pointers, next gate,
and an explicit statement that the decision does not imply runtime MCP
exposure. Missing or invalid dispositions fail closed.

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

Candidate review completion does not mean promotion. Every candidate must have
an explicit `approved_for_review_only`, `blocked`, or `deferred` disposition;
sensitive GET routes may remain blocked. Future agent evidence/results and
streaming activity events must use versioned typed contracts. Callable MCP,
public web search, assistant streaming UX, and action-enabled agent work remain
deferred until the typed API migration, authentication boundary, and separate
safety review are complete.
