# PixEagle Modernization Phase And Slice Map

Last updated: 2026-06-18

This file is the resume anchor after pauses, context compaction, or handoff. Use
it together with:

- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/architecture/pixeagle-modernization-blueprint.md`
- `docs/apis/api-modernization-blueprint.md`
- latest journal entry under `docs/reporting/agent-ops/codex-modernization/journal/`
- latest checkpoint under `docs/reporting/agent-ops/codex-modernization/checkpoints/`

## Global Goals

- Separate vision, tracking, following, telemetry, flight control, API,
  streaming, config, and UI concerns.
- Keep PX4 Offboard command publication independent of frame processing and UI
  state.
- Make `/api/v1` the typed, MCP-friendly public contract surface.
- Keep config, generated schema, docs, dashboard clients, tests, scripts, and
  runtime behavior aligned with one source of truth.
- Remove stale legacy aliases, duplicated docs, backup configs, placeholder
  tests, and misleading safety claims through tracked deprecation gates.
- Back every flight-control-adjacent claim with logs, exact commands, versions,
  configs, and evidence artifacts.

## Completed Slices

| Slice | Status | Primary Issues | Evidence |
| --- | --- | --- | --- |
| Phase 0 baseline/governance | done | PXE-0001, PXE-0002, PXE-0003, PXE-0004, PXE-0005 | `checkpoints/2026-04-30-phase-0-baseline-governance.md` |
| Phase 0 infrastructure docs | done | PXE-0006 | `checkpoints/2026-04-30-phase-0-infrastructure-docs.md` |
| Phase 0 secondary docs | done | PXE-0012 | `checkpoints/2026-04-30-phase-0-secondary-docs.md` |
| Phase 0 test hygiene | done | PXE-0011 | `checkpoints/2026-04-30-phase-0-test-hygiene.md` |
| Phase 0 legacy gimbal docs | done | PXE-0015, PXE-0017 | `checkpoints/2026-04-30-phase-0-legacy-gimbal-docs.md` |
| Phase 0 SITL validation scout | done | PXE-0018, PXE-0019, PXE-0020 | `checkpoints/2026-04-30-phase-0-sitl-validation-scout.md` |
| Phase 0 dashboard debt | done | PXE-0009, PXE-0010 | `checkpoints/2026-05-07-phase-0-dashboard-debt-resume.md`; created follow-up issues PXE-0021 and PXE-0022 |
| May 21 pause/companion drift resume | done | PXE-0022 | `audits/2026-05-21-resume-companion-drift.md` |
| Phase 1 gimbal provider boundary | done | PXE-0016 | `checkpoints/2026-05-21-phase-1-gimbal-provider.md`; follow-up PXE-0023 |
| Phase 2 command freshness | done | PXE-0032 | `checkpoints/2026-05-24-phase-2-command-freshness.md` |
| Phase 2 rate/cadence truth | done | PXE-0030 | `checkpoints/2026-05-29-phase-2-rate-cadence.md` |
| Phase 2 safety truth | done | PXE-0033 | `checkpoints/2026-05-29-phase-2-safety-truth.md`; follow-up PXE-0034 |
| Phase 2 command intent atomicity | done | PXE-0034 | `checkpoints/2026-05-30-phase-2-command-intent.md`; follow-up PXE-0007/PXE-0013 |
| Phase 2 Offboard commander boundary | done | PXE-0007, PXE-0013 | `checkpoints/2026-06-01-phase-2-offboard-commander.md`; follow-up PXE-0035/PXE-0018 |
| Phase 2 MAVLink telemetry freshness | done | PXE-0014 | `checkpoints/2026-06-01-phase-2-mavlink-telemetry-freshness.md`; follow-up PXE-0036 |
| Phase 2 Offboard commander failure policy | done | PXE-0035 | `checkpoints/2026-06-01-phase-2-offboard-commander-failure-policy.md`; follow-up PXE-0018 |
| Phase 2 PX4-in-loop validation harness | done | PXE-0018 | `checkpoints/2026-06-01-phase-2-px4-in-loop-validation-harness.md`; follow-up PXE-0037 now done |
| Phase 3 tracker-in-loop validation | done | PXE-0019 | `checkpoints/2026-06-01-phase-3-tracker-in-loop-validation.md`; follow-up PXE-0038 |
| Phase 3 SITL scenario action/evidence import contract | done | PXE-0037 partial | `checkpoints/2026-06-01-phase-3-sitl-scenario-action-contract.md`; superseded by final PXE-0037 checkpoint |
| Phase 3 PX4 SIH CI validation research | done | PXE-0037, PXE-0039 | `audits/2026-06-02-px4-sih-ci-validation-research.md`; follow-up PXE-0039 now done |
| Phase 3 SITL target-loss injector | done | PXE-0037 partial | `checkpoints/2026-06-02-phase-3-sitl-target-loss-injector.md`; superseded by final PXE-0037 checkpoint |
| Phase 3 SITL video-stall injector | done | PXE-0037 partial | `checkpoints/2026-06-02-phase-3-sitl-video-stall-injector.md`; superseded by final PXE-0037 checkpoint |
| Phase 3 SITL commander publish-failure injector | done | PXE-0037 partial | `checkpoints/2026-06-02-phase-3-sitl-commander-publish-failure-injector.md`; superseded by final PXE-0037 checkpoint |
| Phase 3 SITL MAVLink2REST timeout injector | done | PXE-0037 partial | `checkpoints/2026-06-02-phase-3-sitl-mavlink2rest-timeout-injector.md`; superseded by final PXE-0037 checkpoint |
| Phase 3 SITL MAVSDK disconnect injector | done | PXE-0037 partial | `checkpoints/2026-06-03-phase-3-sitl-mavsdk-disconnect-injector.md`; superseded by final PXE-0037 checkpoint |
| Phase 3 PX4 artifact auto-collection | done | PXE-0037 partial | `checkpoints/2026-06-03-phase-3-px4-artifact-auto-collection.md`; superseded by final PXE-0037 checkpoint |
| Phase 3 structured MavlinkAnywhere route/profile validation | done | PXE-0037 | `checkpoints/2026-06-03-phase-3-structured-mavlinkanywhere-validation.md`; PXE-0037 done; PXE-0042 remains separate |
| Phase 3 lightweight official PX4 SIH CI profile | done | PXE-0039 | `checkpoints/2026-06-03-phase-3-px4-sih-ci-profile.md`; opt-in contract only, no runtime PX4/SITL pass claimed |
| Phase 3 generated RTP/UDP video receiver proof | done | PXE-0040 partial | `checkpoints/2026-06-03-phase-3-generated-rtp-udp-video-receiver-proof.md`; portable evidence at `evidence/2026-06-03-pxe0040-generated-rtp-udp-video-receiver-proof/`; runtime artifacts at `reports/video/20260603T-pxe0040-generated-rtp-udp-proof-v2/`; official Gazebo visual SITL remains open |
| Phase 3 official Gazebo visual profile contract | done | PXE-0040 partial | `checkpoints/2026-06-04-phase-3-official-gazebo-visual-profile-contract.md`; checked-in official profile, wrapper, opt-in workflow, visual artifact imports, and artifact-content validators done; no Docker/PX4/Gazebo runtime pass claimed |
| Phase 3 tracker trace artifacts | done | PXE-0038 | `checkpoints/2026-06-04-phase-3-tracker-trace-artifacts.md`; normalized JSONL schema, guarded AppController runtime hook, strict Gazebo trace validation, and deterministic AppController/follower/CommandIntent smoke done |
| Phase 3 official Gazebo runtime probe | done/incomplete | PXE-0040 partial | `checkpoints/2026-06-04-phase-3-official-gazebo-runtime-probe.md`; Docker access via `sg docker` works, nonexistent `v1.17.0` tag corrected to `v1.17.0-alpha1-1551-g381149fb01` plus repo digest, official image pull/inspect succeeded, container metadata passed in the 45s run, but the 120s official PX4/Gazebo run exited `255` after `Timed out waiting for Gazebo world`; no PixEagle visual SITL pass claimed |
| Phase 3 official SIH runtime probe and log hardening | done/incomplete | PXE-0039, PXE-0042 | `checkpoints/2026-06-04-phase-3-official-sih-runtime-probe.md`; corrected nonexistent `px4io/px4-sitl:v1.17.0` to `v1.17.0-alpha1-1551-g381149fb01` plus repo digest, official SIH container started and stayed alive through the startup window, image/container metadata passed, params and ULog were collected, PX4 stdout capture was bounded/filtered, and the run correctly stayed incomplete because PixEagle, MAVLink2REST, complete MavlinkAnywhere route/profile evidence, scenario results, PixEagle log, and tlog evidence were absent |
| Phase 4 SITL typed actions and PX4 observation gate | done | PXE-0042 | `checkpoints/2026-06-04-phase-4-sitl-typed-actions-px4-observation.md`; typed `/api/v1/actions/*` start/abort resources, required idempotency for confirmed control actions, legacy action audit/deprecation metadata, Phase 2 typed scenario actions, and fail-closed `px4/offboard_observation.json` heartbeat/same-system/tlog/window gate done; no runtime PX4/SITL pass claimed |
| Phase 4 typed MAVLink telemetry health | done | PXE-0036 | `checkpoints/2026-06-04-phase-4-typed-telemetry-health.md`; typed `/api/v1/telemetry/health` separates transport latest-request result, last-success freshness, cached payload availability, consumer guidance, disabled fail-closed freshness, validation-timeout state, claim boundary, and structured errors; dashboard/client adoption completed separately under PXE-0043 |
| Phase 4 dashboard typed telemetry-health adoption | done | PXE-0043 | `checkpoints/2026-06-04-phase-4-dashboard-telemetry-health.md`; dashboard endpoint registry, `useTelemetryHealth()` normalizer, and operational status bar chip now consume `/api/v1/telemetry/health`, distinguish usable/degraded/stale/unavailable/disabled/connecting states, and cover disabled cached payload plus degraded cache-fresh/latest-request-failed cases in frontend tests |
| Phase 4 dashboard tracker-state clarity | done | PXE-0024 | `checkpoints/2026-06-04-phase-4-dashboard-tracker-state-clarity.md`; dashboard tracker runtime normalization distinguishes output-visible, active, stale, not-usable, no-output, checking, and unavailable states; tracker cards/data display/status chips/nav/follow controls consume the normalized state; legacy and typed Offboard-start paths fail closed on absent/stale/unusable tracker output; legacy tracker telemetry and current-status handle `MULTI_TARGET` target visibility plus `has_output`, `usable_for_following`, and `data_is_stale`; deeper typed tracker runtime/API/internal cleanup closed under PXE-0044 |
| Phase 4 typed tracker runtime status | done | PXE-0044 | `checkpoints/2026-06-05-phase-4-typed-tracker-runtime-status.md`; shared tracker runtime evaluator, typed `/api/v1/tracking/runtime-status`, legacy tracker/current compatibility fields, selector/hook migration to typed runtime state, reverse-proxy-safe tracker hooks, and TargetLossHandler fail-closed active+stale/not-usable handling done |
| Phase 4 typed runtime status | done | PXE-0045 | `checkpoints/2026-06-05-phase-4-typed-runtime-status.md`; typed `/api/v1/runtime/status`, shared snapshot helper behind legacy `/status`, mode/subsystem separation, fail-closed local following classification for unsafe Offboard commander state, dashboard smart-mode migration with legacy route fallback and stale-response guards, route inventory/frontend/backend tests, and refreshed companion refs done |
| Phase 4 typed following status | done | PXE-0046 | `checkpoints/2026-06-06-phase-4-typed-following-status.md`; typed `/api/v1/following/status`, follower profile and OffboardCommander publication summary, fail-closed following readiness classification, dashboard follower-status hook migration with legacy telemetry fallback and stale-response guards, route inventory/frontend/backend tests, and follower integration docs correction done |
| Phase 4 typed following telemetry | done | PXE-0047 | `checkpoints/2026-06-06-phase-4-typed-following-telemetry.md`; typed `/api/v1/following/telemetry`, live setpoint-field snapshot with compatibility fallback, optional target-loss/safety/performance diagnostics, dashboard detailed follower-card hook migration with stale-response guards, route inventory/frontend/backend tests, and docs/reporting updates done |
| Phase 4 Follower visualization typed telemetry history | done | PXE-0048 | `checkpoints/2026-06-06-phase-4-follower-page-typed-telemetry-history.md`; Follower visualization page now uses endpoint registry plus typed `/api/v1/following/telemetry` for follower/setpoint history snapshots, legacy route fallback only for missing typed routes, chart-compatible field aliases, bounded history/log growth, initial refresh, stale-response guards, and focused frontend tests |
| Phase 4 typed tracker telemetry history | done | PXE-0049 | `checkpoints/2026-06-06-phase-4-typed-tracker-telemetry-history.md`; typed `/api/v1/tracking/telemetry`, live TrackerOutput geometry fields with compatibility fallback, embedded runtime status, Follower visualization tracker plot migration, route inventory/backend/frontend tests, and docs/reporting updates done |
| Phase 4 API/MCP candidate inventory | done | PXE-0050 | `checkpoints/2026-06-06-phase-4-api-tool-candidate-inventory.md`; generated non-callable `/api/v1` candidate inventory, source hash, risk/sensitivity classification, action/SITL read-only promotion blocks, agent-context docs, generator drift gate in CI/phase0-check, and focused candidate tests done; no MCP endpoint, registry, `tools/list`, or callable tool exposure added |
| Phase 4 docs-stage agent registry and policy | done | PXE-0051 | `checkpoints/2026-06-06-phase-4-docs-stage-agent-registry-policy.md`; review-only `agent_tools.yaml` and default-deny `agent_policy.yaml` added for the six typed process-local status/telemetry GET candidates; generator coverage now detects unsafe registry/policy drift; all tools remain `callable: false`, `mcp_exposure: none`, and unpromoted; no runtime MCP endpoint, executor, `tools/list`, or `tools/call` added |
| Phase 4 API v1 route registry extraction | done | PXE-0052 | `checkpoints/2026-06-06-phase-4-api-v1-route-registry-extraction.md`; all 14 typed `/api/v1` route metadata specs moved into static `ApiV1RouteSpec` metadata and `FastAPIHandler` delegates registration; static route inventory and candidate generator parse both source files, preserve 129 HTTP routes and 14 `/api/v1` candidates, and keep all agent/MCP candidates non-callable |
| Phase 4 API v1 contract extraction | done | PXE-0053 | `checkpoints/2026-06-06-phase-4-api-v1-contract-extraction.md`; typed `/api/v1` Pydantic request/response models, claim boundaries, and response metadata moved to `src/classes/api_v1_contracts.py`; `FastAPIHandler` imports/re-exports them for migration compatibility; generated candidate provenance now hashes contracts, and tests prevent `API*`/`SITL*` contract drift back into the handler |
| Phase 4 API v1 path/error boundary | done | PXE-0054 | `checkpoints/2026-06-07-phase-4-api-v1-path-error-boundary.md`; canonical typed `/api/v1` path constants and route-family predicates moved to `src/classes/api_v1_paths.py`, structured error-envelope construction moved to `src/classes/api_v1_errors.py`, route specs consume shared path constants, static parsers resolve those constants without runtime startup, candidate provenance now hashes paths, and tests prevent path/error helper drift back into the handler |
| Phase 4 API v1 action boundary | done | PXE-0055 | `checkpoints/2026-06-07-phase-4-api-v1-action-boundary.md`; process-local action-resource storage, idempotency replay, record construction, legacy action audit attachment, and confirmation/idempotency precondition failure helpers moved to `src/classes/api_v1_actions.py`; `FastAPIHandler` keeps migration wrappers only; candidate provenance now hashes actions, and tests prevent action-store internals/direct UUID record construction from drifting back into the handler |
| Phase 4 API v1 snapshot boundary | done | PXE-0056 | `checkpoints/2026-06-07-phase-4-api-v1-snapshot-boundary.md`; process-local runtime/following/tracking read-state snapshot builders moved to `src/classes/api_v1_snapshots.py`; `FastAPIHandler` keeps migration wrappers only; candidate provenance now hashes snapshots, and tests prevent snapshot semantics/claim-boundary constants from drifting back into the handler |
| Phase 4 API v1 telemetry-health boundary | done | PXE-0057 | `checkpoints/2026-06-07-phase-4-api-v1-telemetry-health-boundary.md`; typed MAVLink telemetry-health manager delegation and fail-closed unavailable fallback semantics moved to `src/classes/api_v1_telemetry.py`; the route method remains an error-boundary wrapper only; candidate provenance now hashes telemetry helpers, and tests prevent fallback semantics/claim-boundary imports from drifting back into the handler |
| Phase 4 API v1 SITL injection boundary | done | PXE-0058 | `checkpoints/2026-06-07-phase-4-api-v1-sitl-injection-boundary.md`; validation-only SITL injection gates, `TrackerOutput`/frame-status payload builders, dry-run summaries, synthetic fault dispatch, and AppController validation-hook calls moved to `src/classes/api_v1_sitl.py`; `FastAPIHandler` keeps compatibility wrappers only; candidate provenance now hashes SITL helpers, and tests prevent SITL gate strings/response codes/validation hooks/transport-scope metadata/`TrackerOutput` construction from drifting back into the handler |
| Phase 4 API v1 action route boundary | done | PXE-0059 | `checkpoints/2026-06-07-phase-4-api-v1-action-route-boundary.md`; guarded typed Offboard-start/operator-abort action execution and action-resource lookup moved to `src/classes/api_v1_actions.py`; `FastAPIHandler` keeps one-call route wrappers only; candidate provenance stays current, tests prevent typed action route bodies from drifting back into the handler, and focused action tests cover concurrent idempotent operator-abort replay |
| Phase 4 API v1 read route boundary | done | PXE-0060 | `checkpoints/2026-06-09-phase-4-api-v1-read-route-boundary.md`; typed runtime/following/tracking/telemetry-health read-route error boundaries moved to `src/classes/api_v1_read_routes.py`; `FastAPIHandler` keeps one-call read route wrappers only; candidate provenance now hashes read routes, and tests prevent typed read-route error strings from drifting back into the handler |
| Phase 4 legacy control route boundary | done | PXE-0061 | `checkpoints/2026-06-10-phase-4-legacy-control-route-boundary.md`; former `/commands/start_offboard_mode` and `/commands/cancel_activities` execution bodies moved to `src/classes/api_legacy_control_routes.py` before alias retirement; `FastAPIHandler` kept one-call wrappers at that checkpoint; generated candidate provenance hashes the helper because guarded typed action candidates still use those internal executors; tests prevent dangerous control execution bodies from drifting back into the handler |
| Phase 4 legacy Offboard stop route boundary | done | PXE-0062 | `checkpoints/2026-06-10-phase-4-legacy-offboard-stop-boundary.md`; former `/commands/stop_offboard_mode` execution body moved to `src/classes/api_legacy_control_routes.py` before alias retirement; `FastAPIHandler` kept a one-call wrapper at that checkpoint; static tests prevent Offboard-stop emergency-cleanup/idempotency strings from drifting back into the handler; focused tests cover inactive idempotency, active disconnect delegation, emergency cleanup after disconnect failure, cleanup-failure reporting, and unreadable final-state fallback |
| Phase 4 typed Offboard stop action | done | PXE-0063 | `checkpoints/2026-06-11-phase-4-typed-offboard-stop-action.md`; typed `POST /api/v1/actions/offboard-stop` added with confirmation, dry-run, required idempotency for confirmed mutations, process-local action records, idempotent replay, per-key concurrency serialization, structured route metadata/errors, guarded non-callable candidate classification, dashboard Start/Stop/Cancel action migration, and local fail-closed semantics for cleanup warnings or still-active following; the later Offboard/operator action-only slice retired the public `/commands/stop_offboard_mode` HTTP alias |
| Phase 4 companion runtime reconciliation | done | PXE-0022 | `checkpoints/2026-06-11-phase-4-companion-runtime-reconciliation.md`; exact current MDS/MavlinkAnywhere/Smart Wi-Fi Manager review, canonical companion ownership/auth/profile/secret/version/evidence/agent-boundary contract, active routing/SITL/API/architecture/exposure docs alignment, docs guardrails, and bounded read-only local probe done; follow-up runtime auth/exposure, SITL sidecar-evidence, and candidate-disposition work tracked as PXE-0064/PXE-0065/PXE-0066; no sidecar mutation or routing/PX4/SITL success claimed |
| Phase 4 API exposure containment foundation | done | PXE-0064 partial | `checkpoints/2026-06-12-phase-4-api-exposure-containment.md`; backend, dashboard, and MAVLink2REST defaults are local-only; `API_EXPOSURE_MODE` governs checked-in and legacy remote binds; wildcard CORS and contradictory local-only origins fail closed; Host/DNS-rebinding, browser Origin/Fetch-Metadata, and WebSocket Host/Origin checks run before route execution/accept; launchers/docs no longer advertise default LAN exposure; guardrail tests cover defaults and stale exposure guidance; production auth/CSRF/scopes/media auth/legacy mutation retirement remain open under PXE-0064 |
| Phase 4 API security policy foundation | done | PXE-0064 partial | `checkpoints/2026-06-13-phase-4-api-security-policy-foundation.md`; typed principal/scope/role contracts and a declarative default-deny route policy now cover every declared route plus implicit FastAPI docs routes; exact-coverage tests prove route classification, least-privilege session roles, exact bearer scopes, local-only legacy/admin/SITL boundaries, and no callable MCP/tool exposure |
| Phase 4 API auth runtime foundation | done | PXE-0064 partial | `checkpoints/2026-06-13-phase-4-api-auth-runtime-foundation.md`; HTTP/MJPEG route execution and video/WebRTC WebSocket acceptance now pass through route authorization; `local_compat` is same-host socket-only and refuses `Host`/proxy-forwarded local proof; non-loopback API clients use scoped hashed bearer records from an external token file; query-string tokens are rejected; at that checkpoint browser sessions and CSRF were still open, and later browser-session, dashboard client/media, security-audit, Offboard/operator action-only, and typed tracking action slices closed those portions; remaining PXE-0064 work is operator credential/TLS hardening, retirement of remaining legacy aliases, and broader adversarial browser/session/media tests |
| Phase 4 browser-session auth foundation | done | PXE-0064 partial | `checkpoints/2026-06-14-phase-4-browser-session-auth-foundation.md`; `API_AUTH_MODE=browser_session` now loads external PBKDF2-SHA256 user records, exposes typed `/api/v1/auth/session`, `/api/v1/auth/login`, and `/api/v1/auth/logout`, creates HttpOnly cookie sessions, validates session-bound CSRF on browser mutations, throttles failed login attempts, enables credentialed exact-origin CORS only in browser-session mode, keeps auth route bodies outside `FastAPIHandler`, and updates API/MCP candidate provenance with no callable tool exposure; later dashboard auth client/media, security-audit, Offboard/operator action-only, and typed tracking action slices closed the frontend, durable-audit, and dangerous-alias portions; remaining work is TLS/operator credential hardening, retirement of remaining legacy aliases, and broader adversarial tests |
| Phase 4 dashboard auth client/media foundation | done | PXE-0064 partial | `checkpoints/2026-06-14-phase-4-dashboard-auth-client-media.md`; dashboard now has one credential-aware `apiClient` boundary for `fetch`, axios, session CSRF, auth-failure refresh, cookie-session MJPEG/WebSocket/WebRTC construction, and protected blob downloads/playback; app shell has login/logout/session UX; operator controls honor session scopes; source guardrails reject raw production `fetch`, direct axios package imports, direct `new WebSocket`, and protected endpoint `href` bypasses; later security-audit, Offboard/operator action-only, and typed tracking action slices closed the audit-event and dangerous-alias portions; remaining work is TLS/operator credential hardening, retirement of remaining legacy aliases, and broader adversarial browser/session/media tests |
| Phase 4 durable API security-audit foundation | done | PXE-0064 partial | `checkpoints/2026-06-16-phase-4-api-security-audit-foundation.md`; added `src/classes/api_security_audit.py` for sanitized append-only JSONL security events with bounded rotation; HTTP, video WebSocket, WebRTC signaling, login, and logout paths record auth decisions/outcomes without credential material; allowed mutation/security-critical requests fail closed if audit cannot be written; `Streaming.API_SECURITY_AUDIT_*` config and generated schema are aligned; API/MCP candidate provenance includes the audit module; later Offboard/operator action-only and typed tracking action slices retired or replaced dangerous public command paths; remaining work is TLS/operator credential hardening, retirement of remaining legacy aliases, and broader adversarial browser/session/media tests |
| Phase 4 Offboard/operator action-only alias retirement | done | PXE-0064 partial | `checkpoints/2026-06-16-phase-4-offboard-operator-action-only-retirement.md`; retired public HTTP registration for `/commands/start_offboard_mode`, `/commands/stop_offboard_mode`, and `/commands/cancel_activities`; dashboard endpoint registry and Start/Stop/Abort classification now use only typed `/api/v1/actions/*`; API security policy, route inventory, generated API/MCP candidate inventory, and active docs now record those aliases as retired; internal compatibility executors remain only as implementation details until the lower-level control executor is refactored; no PX4/SITL/HIL/field success claimed |
| Phase 4 typed tracking action foundation | done | PXE-0064 partial | `checkpoints/2026-06-16-phase-4-typed-tracking-actions.md`; typed `/api/v1/actions/tracking-start` and `/api/v1/actions/tracking-stop` action resources added with confirmation, dry-run, required idempotency for confirmed mutations, process-local action records, guarded non-callable API/MCP candidate classification, dashboard ROI start/stop migration, and local-only compatibility aliases for `/commands/start_tracking` and `/commands/stop_tracking` pending a later retirement gate |
| Phase 4 typed tracking utility actions | done | PXE-0064 partial | `checkpoints/2026-06-17-phase-4-typed-tracking-utility-actions.md`; typed `/api/v1/actions/tracking-redetect`, `/api/v1/actions/segmentation-toggle`, `/api/v1/actions/smart-mode-toggle`, and `/api/v1/actions/smart-click` action resources added with confirmation, dry-run, idempotent replay for confirmed mutations, action records, guarded non-callable API/MCP candidate classification, dashboard redetect/segmentation/smart-mode/smart-click migration, local-only compatibility aliases pending retirement, smart-click no-target failure truthfulness, `actions:execute` dashboard scope gating, and reviewer-approved fixes |
| Phase 4 QGC video compatibility reconciliation | done | PXE-0067 | `checkpoints/2026-06-17-phase-4-qgc-video-compatibility.md`; reviewed QGroundControl PR #13594 at head `f0a4feba`, restored same-host native QGC WebSocket compatibility without weakening remote/browser Origin or media auth gates, documented the direct HTTP/WS versus GStreamer UDP/RTP QGC matrix, aligned active video docs with current `Streaming`/`GStreamer` keys, added stale-doc guard coverage, and regenerated API/MCP candidate provenance; QGC branch merge/auth-header work remains a separate follow-up and no PX4/SITL/HIL/field or service/deployment action was claimed |
| Phase 4 remote media security policy | done | PXE-0069 | `checkpoints/2026-06-17-phase-4-remote-media-security-policy.md`; clarified normal Pi-to-GCS operation without opening anonymous backend media, added `Streaming.API_ALLOWED_HOSTS` to separate backend Host allowlisting from browser CORS origins, documented local-dev, field-QGC RTP/UDP, remote-browser, remote-native HTTP/WS, and rejected anonymous-LAN profiles, added stale video-query and OSD-key docs guardrails, and recorded QGC authenticated remote HTTP/WS implementation as PXE-0070; no QGC branch mutation, PX4/SITL/HIL/field or service/deployment action was claimed |
| Phase 4 QGC source-profile and demo policy | done | PXE-0071 | `checkpoints/2026-06-17-phase-4-qgc-source-profile-demo-policy.md`; preserved generic QGC HTTP/HTTPS MJPEG and WebSocket support for non-PixEagle sources, documented PixEagle as a stricter configured source profile rather than QGC core behavior, clarified the PixEagle config contract for generic QGC interop (`API_ALLOWED_HOSTS`, exact host authority, future Authorization/Origin/TLS settings, `media:read`-only video token), clarified that beginner full-dashboard LAN demos should use generated browser-session credentials while anonymous demos must be media-only, posted QGC PR clarification comment `https://github.com/mavlink/qgroundcontrol/pull/13594#issuecomment-4731276373`, and updated PXE-0068/PXE-0070 gates plus docs guardrails; no QGC branch mutation, PX4/SITL/HIL/field or service/deployment action was claimed |
| Phase 4 setup-profile foundation | done | PXE-0068 partial | `checkpoints/2026-06-17-phase-4-setup-profile-foundation.md`; added explicit setup-profile tooling, `local_dev` and `field_qgc_video` profile application, fail-closed defined remote/unsafe profiles, Make targets, QGC UDP/RTP default port `5600` alignment, init/install clean-clone default behavior, deployment-only service opt-in, Windows port fallback, companion/troubleshooting cleanup, legacy telemetry WebSocket labeling, and setup-profile/docs regression guards; PXE-0068 remains open for credential-generating remote profile automation and media/service follow-ups |
| Phase 4 binary download provenance | done | PXE-0068 partial | `checkpoints/2026-06-17-phase-4-binary-download-provenance.md`; added shared MAVSDK Server/MAVLink2REST binary manifest, exact asset pins and SHA-256 digests, Linux/Windows dry-run plan output, checksum verification before install, provenance JSONL, explicit override policy, no fallback tag probing, init verification for existing binaries, docs, CI/Phase 0 guardrails, and reviewer fixes; no binary download/install, service/deployment, PX4/SITL/HIL/field, or runtime claims |
| Phase 4 API/MCP candidate disposition governance | done | PXE-0066 | `checkpoints/2026-06-18-phase-4-api-mcp-candidate-disposition.md`; generated inventory now assigns every `/api/v1` candidate an explicit review disposition with owner/rationale/evidence/next gate; current split is 6 approved-for-review-only process-local GET candidates, 13 blocked auth/action/audit candidates, and 5 deferred SITL validation-stimulus candidates; policy and registry keep all candidates non-callable, unpromoted, and outside runtime MCP exposure |
| Phase 4 SITL sidecar evidence hardening | done | PXE-0065 | `checkpoints/2026-06-18-phase-4-sitl-sidecar-evidence-hardening.md`; maintained SITL plans now declare MavlinkAnywhere version/capability policy, dry-runs expose the policy, runtime evidence captures installed dashboard version, semantic checks classify unavailable/auth/unsupported/unprepared/prepared routing, accepted evidence requires `prepared_routing`, and secret scanning blocks credential-bearing text artifacts without echoing values; no sidecar mutation or runtime PX4/SITL pass claimed |

## Active Slice

Phase 4 API/MCP modernization. PXE-0042 through PXE-0049 are done for typed
actions, telemetry health, runtime/following/tracker status and telemetry, and
dashboard migration of the touched consumers. PXE-0050 is done for the
generated non-callable API/MCP candidate inventory: all current `/api/v1` HTTP
routes are represented once, only the six typed process-local status/telemetry
GET routes are unpromoted read-only candidates, and action/SITL routes are
blocked from read-only promotion. PXE-0051 is done for docs-stage
`agent_tools.yaml` and `agent_policy.yaml`: the six reviewed candidates are
registered as review-only/unexposed, policy denies execution and
auto-promotion, and generator coverage detects unsafe registry/policy drift.
PXE-0052 is done for first route-family extraction: typed `/api/v1` route
metadata specs now live in `src/classes/fastapi_api_v1_routes.py`,
`FastAPIHandler` delegates registration, and static guardrails parse both route sources without
changing route inventory, candidate classification, or MCP exposure. PXE-0053
is done for first contract extraction: typed `/api/v1` Pydantic contracts,
claim boundaries, and response metadata now live in
`src/classes/api_v1_contracts.py`, are re-exported through `fastapi_handler.py`
for compatibility, and are included in generated candidate provenance. PXE-0054
is done for path/error boundary extraction: canonical typed `/api/v1` path
constants and route-family predicates now live in `src/classes/api_v1_paths.py`,
structured error-envelope construction lives in `src/classes/api_v1_errors.py`,
the route registry consumes shared path constants, and static guardrails resolve
those constants without starting runtime subsystems. PXE-0055 is done for
action-resource boundary extraction: process-local action storage, idempotency
replay, record construction, legacy action audit attachment, and action
precondition failure helpers now live in `src/classes/api_v1_actions.py`, while
`FastAPIHandler` keeps migration wrappers only. PXE-0056 is done for read-state
snapshot extraction: process-local runtime, following, and tracking snapshot
semantics now live in `src/classes/api_v1_snapshots.py` with handler migration
wrappers retained for compatibility. PXE-0057 is done for telemetry health
extraction: typed MAVLink telemetry-health manager delegation and the
fail-closed unavailable fallback now live in `src/classes/api_v1_telemetry.py`
with the route method retained as an error-boundary wrapper. PXE-0058 is done
for SITL validation-stimulus extraction: validation-only injection gates,
payload construction, dry-run summaries, and AppController validation-hook
dispatch now live in `src/classes/api_v1_sitl.py` while `FastAPIHandler` keeps
compatibility wrappers only. PXE-0059 is done for guarded typed action-route
execution extraction: Offboard-start/operator-abort action execution and
action-resource lookup now live in `src/classes/api_v1_actions.py`, while
`FastAPIHandler` keeps one-call route wrappers. PXE-0060 is done for typed
read-route error-boundary extraction: runtime/following/tracking/telemetry
health read-route error handling now lives in `src/classes/api_v1_read_routes.py`,
while `FastAPIHandler` keeps one-call read route wrappers. PXE-0061 is done for
legacy control compatibility-route extraction: legacy Offboard start and
operator cancel bodies now live in `src/classes/api_legacy_control_routes.py`,
while `FastAPIHandler` keeps one-call wrappers and candidate provenance hashes
that helper until the legacy aliases can be removed. PXE-0062 is done for the
remaining legacy Offboard stop route body: stop execution now lives in the same
legacy-control helper, while `FastAPIHandler` keeps a one-call wrapper and
focused tests cover inactive, active, emergency-cleanup, cleanup-failure, and
unreadable-final-state stop behavior. PXE-0063 is done for the typed
Offboard-stop action/deprecation path: `/api/v1/actions/offboard-stop` now has
typed action semantics, dashboard Start Following, Stop Following, and Cancel
Tracker use typed action endpoints, and legacy stop is deprecated with action
audit plus fail-closed local warning/cleanup-error/active-state reporting.
PXE-0064 is in progress: the first containment foundation is done, so
checked-in backend/dashboard/MAVLink2REST exposure is local-only, contradictory
local-only bind/CORS configuration fails closed, Host/Origin/fetch-site and
WebSocket Host/Origin checks guard the process boundary, and active docs no
longer normalize direct LAN exposure. The declarative API security policy
foundation is also complete: every declared route plus implicit docs routes now
has a default-deny classification, exact route coverage tests, and
least-privilege scope modeling. The first runtime-auth foundation is complete:
HTTP/MJPEG route execution plus video/WebRTC WebSocket acceptance use the route
policy, same-host `local_compat` no longer trusts `Host` or proxy-forwarded
client metadata, non-loopback API clients can use scoped hashed bearer records,
and query-string tokens are rejected. The browser-session auth foundation is
also complete: external hashed browser users, typed auth/session routes,
HttpOnly cookie sessions, session-bound CSRF, process-local failed-login
throttling, and credentialed exact-origin CORS are implemented. The dashboard
auth client/media foundation is also complete: one frontend client now owns
credentialed API requests, session CSRF, login/logout/session UX, cookie-session
media construction, protected blob downloads/playback, and scope-aware operator
controls. The durable security-audit foundation is also complete: route auth,
media WebSocket/WebRTC, login, and logout outcomes are written as sanitized
JSONL events, and allowed mutation/security-critical requests fail closed if
audit cannot be written. Offboard start, Offboard stop, and operator abort are
now typed-action-only over HTTP; the former `/commands/*` aliases for those
actions are not registered. PXE-0064 remains open for operator credential/TLS
hardening, retirement of remaining legacy tracking/control compatibility
aliases, and broader adversarial browser/session/media tests. No runtime MCP endpoint,
executor, `tools/list`, `tools/call`, or callable tool surface exists
from these slices. These are still unit/contract evidence only; no runtime
PX4/SITL pass is claimed. Official Gazebo runtime proof (PXE-0040) remains open
for a native GUI/GPU host, a stronger headless runner, or a separately proven
official-image startup workaround. Official SIH L2 probing starts a pinned PX4
container and collects metadata/params/ULog/bounded logs, but no accepted
PixEagle/PX4 interaction pass is claimed until PixEagle, MAVLink2REST,
MavlinkAnywhere routing, typed scenario execution, PX4 observation artifacts,
and safety outcomes are all present. Continue with broader `/api/v1` migration
and router extraction, API authentication/exposure hardening, SITL sidecar
evidence hardening, plus dashboard toolchain modernization (PXE-0008,
PXE-0064, PXE-0065, PXE-0021)
while keeping full
runtime L2/L3/L4 validation operator-gated.

Audit artifact:

- `audits/2026-06-02-final-implementation-roadmap.md`
- `checkpoints/2026-06-03-phase-3-px4-sih-ci-profile.md`
- `checkpoints/2026-06-03-phase-3-generated-rtp-udp-video-receiver-proof.md`
- `checkpoints/2026-06-04-phase-3-official-gazebo-visual-profile-contract.md`
- `checkpoints/2026-06-04-phase-3-tracker-trace-artifacts.md`
- `checkpoints/2026-06-04-phase-3-official-gazebo-runtime-probe.md`
- `checkpoints/2026-06-04-phase-3-official-sih-runtime-probe.md`
- `checkpoints/2026-06-04-phase-4-sitl-typed-actions-px4-observation.md`
- `checkpoints/2026-06-04-phase-4-typed-telemetry-health.md`
- `checkpoints/2026-06-04-phase-4-dashboard-telemetry-health.md`
- `checkpoints/2026-06-04-phase-4-dashboard-tracker-state-clarity.md`
- `checkpoints/2026-06-05-phase-4-typed-tracker-runtime-status.md`
- `checkpoints/2026-06-05-phase-4-typed-runtime-status.md`
- `checkpoints/2026-06-06-phase-4-typed-following-status.md`
- `checkpoints/2026-06-06-phase-4-typed-following-telemetry.md`
- `checkpoints/2026-06-06-phase-4-follower-page-typed-telemetry-history.md`
- `checkpoints/2026-06-06-phase-4-typed-tracker-telemetry-history.md`
- `checkpoints/2026-06-06-phase-4-api-tool-candidate-inventory.md`
- `checkpoints/2026-06-06-phase-4-docs-stage-agent-registry-policy.md`
- `checkpoints/2026-06-06-phase-4-api-v1-route-registry-extraction.md`
- `checkpoints/2026-06-06-phase-4-api-v1-contract-extraction.md`
- `checkpoints/2026-06-07-phase-4-api-v1-path-error-boundary.md`
- `checkpoints/2026-06-07-phase-4-api-v1-action-boundary.md`
- `checkpoints/2026-06-07-phase-4-api-v1-snapshot-boundary.md`
- `checkpoints/2026-06-07-phase-4-api-v1-telemetry-health-boundary.md`
- `checkpoints/2026-06-07-phase-4-api-v1-sitl-injection-boundary.md`
- `checkpoints/2026-06-07-phase-4-api-v1-action-route-boundary.md`
- `checkpoints/2026-06-09-phase-4-api-v1-read-route-boundary.md`
- `checkpoints/2026-06-10-phase-4-legacy-control-route-boundary.md`
- `checkpoints/2026-06-10-phase-4-legacy-offboard-stop-boundary.md`
- `checkpoints/2026-06-11-phase-4-typed-offboard-stop-action.md`
- `checkpoints/2026-06-12-phase-4-api-exposure-containment.md`
- `checkpoints/2026-06-13-phase-4-api-security-policy-foundation.md`
- `checkpoints/2026-06-13-phase-4-api-auth-runtime-foundation.md`
- `checkpoints/2026-06-14-phase-4-browser-session-auth-foundation.md`
- `checkpoints/2026-06-14-phase-4-dashboard-auth-client-media.md`

Recently completed Offboard commander follow-up issues:

- PXE-0025: Offboard start failure can become local success. Done in
  `checkpoints/2026-05-21-phase-2-offboard-fail-open-fixes.md`.
- PXE-0026: MAVSDK command send failures do not propagate. Done in
  `checkpoints/2026-05-21-phase-2-offboard-fail-open-fixes.md`.
- PXE-0027: Operator cancel/stop paths are not flight-control-complete. Done in
  `checkpoints/2026-05-21-phase-2-operator-abort-fix.md`.
- PXE-0028: Offboard-exit callback scheduling is not thread-safe. Done in
  `checkpoints/2026-05-21-phase-2-offboard-fail-open-fixes.md`.
- PXE-0029: SetpointSender shutdown can be skipped by missing status method.
  Done in `checkpoints/2026-05-21-phase-2-offboard-fail-open-fixes.md`.
- PXE-0030: Rate config units and publish cadence are inconsistent. Done in
  `checkpoints/2026-05-29-phase-2-rate-cadence.md`.
- PXE-0031: Target-loss/inactive follower paths can skip safe publication. Done
  in `checkpoints/2026-05-22-phase-2-target-loss-safe-publication.md`.
- PXE-0032: Video/frame freshness is not a command-freshness contract. Done in
  `checkpoints/2026-05-24-phase-2-command-freshness.md`.
- PXE-0033: Safety truth is split and sometimes fail-open. Done in
  `checkpoints/2026-05-29-phase-2-safety-truth.md`.
- PXE-0034: Concrete followers still mutate shared setpoint state instead of
  emitting an atomic command intent. Done in
  `checkpoints/2026-05-30-phase-2-command-intent.md`.
- PXE-0007/PXE-0013: Dedicated Offboard commander boundary implemented and
  docs aligned. Done in
  `checkpoints/2026-06-01-phase-2-offboard-commander.md`.
- PXE-0014: MAVLink telemetry timeout/retry/staleness config and API freshness
  visibility implemented. Done in
  `checkpoints/2026-06-01-phase-2-mavlink-telemetry-freshness.md`; typed
  telemetry-health semantics remain PXE-0036.
- PXE-0035: OffboardCommander publish failures and dependency validation
  failures now cross typed thresholds, surface failed/degraded health, serialize
  stop/final publish behavior, and stop local following through tested
  fail-closed cleanup. Done in
  `checkpoints/2026-06-01-phase-2-offboard-commander-failure-policy.md`.
- PXE-0018: checked-in PX4/SITL plan library, dry-run/probe/guarded-execute
  harness, helper scripts, opt-in pytest markers, CI/Make marker exclusions,
  and evidence contract implemented. Done in
  `checkpoints/2026-06-01-phase-2-px4-in-loop-validation-harness.md`.
- PXE-0019: deterministic synthetic video and gimbal replay fixtures now drive
  tracker outputs through public follower/control contracts, including stale
  visual and stale gimbal fail-closed paths. Done in
  `checkpoints/2026-06-01-phase-3-tracker-in-loop-validation.md`.
- PXE-0037: SITL scenario executor, owned fault injectors, PX4 artifact import
  and container auto-collection, manifest failure precedence, and structured
  MavlinkAnywhere route/profile validation are implemented. Done in
  `checkpoints/2026-06-03-phase-3-structured-mavlinkanywhere-validation.md`.
- PXE-0039: opt-in official PX4 SIH local/GitHub Actions profile implemented
  with dry-run default, probe-only mode, guarded PX4-only execution, artifact
  upload, Make targets, docs, and tests. Done in
  `checkpoints/2026-06-03-phase-3-px4-sih-ci-profile.md`.
- PXE-0040 prerequisite: generated H.264 RTP/UDP receiver proof implemented
  with a dry-run contract tool, guarded local `videotestsrc` sender evidence,
  async UDP/GStreamer `VideoHandler` path, fresh frame hashes, and post-stop
  stale/unusable frame statuses. Independent review blockers around reconnect
  lifecycle, stale acceptance strictness, caps ordering, weak docs, and
  portable artifacting were fixed. Done in
  `checkpoints/2026-06-03-phase-3-generated-rtp-udp-video-receiver-proof.md`.
- PXE-0040 profile contract: official PX4 Gazebo visual L4 plan, wrapper,
  opt-in workflow, Make targets, visual artifact import flags, and
  artifact-content validators are implemented. Review blockers around
  file-name-only evidence, weak scenario wording, and image/container digest
  policy were fixed. Done in
  `checkpoints/2026-06-04-phase-3-official-gazebo-visual-profile-contract.md`.
- PXE-0038 trace contract: normalized tracker/offboard JSONL helpers, guarded
  AppController runtime trace hook, strict Gazebo trace validators,
  deterministic AppController/follower/CommandIntent smoke, non-finite JSON
  rejection, and tracker docs are implemented. Done in
  `checkpoints/2026-06-04-phase-3-tracker-trace-artifacts.md`.
- PXE-0042: Phase 2 SITL start/abort actions now use typed `/api/v1/actions/*`
  resources with confirmation, required idempotency, dry-run/replay semantics,
  action audit records, legacy deprecation metadata, and `px4/offboard_observation.json`
  acceptance requiring PX4 heartbeat identity, same-system tlog setpoints, and
  scenario-local cadence windows. Done in
  `checkpoints/2026-06-04-phase-4-sitl-typed-actions-px4-observation.md`.
- PXE-0063: typed Offboard stop now has `POST /api/v1/actions/offboard-stop`
  with confirmation, dry-run, required idempotency, replay, action audit, and
  dashboard Start/Stop/Cancel typed action adoption. Legacy stop remains as a
  deprecated compatibility alias but now reports failure for cleanup
  warnings/errors, emergency cleanup failures, or a still-active local
  following state. Done in
  `checkpoints/2026-06-11-phase-4-typed-offboard-stop-action.md`.
- PXE-0064 first containment foundation: backend/dashboard/MAVLink2REST
  checked-in and managed-launcher defaults are local-only; broad exposure now
  requires explicit `trusted_lan_legacy`; Host/Origin/fetch-site and WebSocket
  Host/Origin checks guard the unauthenticated process boundary; docs and guardrails
  no longer normalize default LAN exposure. At that checkpoint PXE-0064 still
  had authentication/session work open; the later policy, runtime-auth, and
  browser-session foundations have since closed the backend auth/CSRF pieces.
  Later dashboard client/media and security-audit foundations closed the
  frontend and audit-event portions, and the later Offboard/operator
  action-only slice retired the dangerous public command aliases. Remaining
  PXE-0064 work is operator credential/TLS hardening, retirement of remaining
  legacy aliases, and broader adversarial tests. Done in
  `checkpoints/2026-06-12-phase-4-api-exposure-containment.md`.
- PXE-0064 declarative API security policy foundation: typed principal/scope
  contracts, default-deny classification, exact declared-route and implicit
  docs route coverage, least-privilege viewer/operator/admin modeling, exact
  bearer scopes, session CSRF semantics, local-only legacy handling, and API/MCP
  provenance updates. Done in
  `checkpoints/2026-06-13-phase-4-api-security-policy-foundation.md`.
- PXE-0064 runtime auth foundation: route policy is enforced before HTTP/MJPEG
  route execution and before video/WebRTC WebSocket acceptance; same-host
  `local_compat` refuses `Host` and proxy-forwarded local proof; external
  hashed bearer token records authorize non-loopback machine API clients with
  exact scopes; query-string tokens are rejected; WebRTC/WebSocket docs and
  API/MCP candidate provenance were reconciled. At that checkpoint browser
  sessions and CSRF were still open; the later browser-session foundation added
  external user records, auth routes, HttpOnly sessions, session CSRF, and
  login throttling. Later dashboard client/media and security-audit foundations
  closed the frontend and audit-event portions, and the later
  Offboard/operator action-only slice retired the dangerous public command
  aliases. PXE-0064 remains open for operator credential/TLS hardening,
  retirement of remaining legacy aliases, and broader adversarial tests.
  Done in `checkpoints/2026-06-13-phase-4-api-auth-runtime-foundation.md`.
- PXE-0036: backend/API typed MAVLink telemetry health now separates latest
  request result, last-success freshness, cached payload availability, consumer
  guidance, validation timeout state, disabled fail-closed freshness, and
  structured `/api/v1` errors. Done in
  `checkpoints/2026-06-04-phase-4-typed-telemetry-health.md`; dashboard/client
  uptake was completed separately as PXE-0043.
- PXE-0043: dashboard endpoint registry, `useTelemetryHealth()` normalizer, and
  operational status bar chip now consume `/api/v1/telemetry/health`, normalize
  raw payload values into display labels, compute `usableForFollowing`, and
  distinguish usable/degraded/stale/unavailable/disabled/connecting states.
  Done in `checkpoints/2026-06-04-phase-4-dashboard-telemetry-health.md`.
- PXE-0024: dashboard tracker runtime state now has a shared normalizer,
  tracker cards/data display/status chips/nav chips distinguish visible output,
  active tracking, stale output, not-usable output, no output, checking, and
  unavailable states, follow controls and legacy/typed Offboard-start paths
  require `usable_for_following=true`, and legacy tracker telemetry plus
  current-status include targets-only `MULTI_TARGET` visibility,
  `has_output`, `usable_for_following`, and `data_is_stale`. Done in
  `checkpoints/2026-06-04-phase-4-dashboard-tracker-state-clarity.md`.
- PXE-0044: typed tracker runtime status now has a shared backend evaluator,
  `GET /api/v1/tracking/runtime-status`, compatibility fields on
  `/api/tracker/current` and `/api/tracker/current-status`, dashboard selector
  and status-hook adoption, reverse-proxy-safe tracker hooks, and target-loss
  fail-closed behavior for active+stale or active+not-usable input. Done in
  `checkpoints/2026-06-05-phase-4-typed-tracker-runtime-status.md`.
- PXE-0045: typed PixEagle process-local runtime status now has
  `GET /api/v1/runtime/status`, shared legacy `/status` snapshot assembly,
  explicit mode/subsystem separation, structured `/api/v1` errors, dashboard
  `useSmartModeStatus()` adoption through the endpoint registry, legacy route
  fallback for missing typed endpoints, stale-response guards, fail-closed
  classification for unsafe Offboard commander state while following, and
  refreshed current companion refs. Done in
  `checkpoints/2026-06-05-phase-4-typed-runtime-status.md`.
- PXE-0046: typed process-local following status now has
  `GET /api/v1/following/status`, follower profile identity, OffboardCommander
  publication summary, fail-closed following readiness classification,
  structured `/api/v1` errors, dashboard `useFollowerStatus()` adoption through
  the endpoint registry, legacy fallback for missing typed endpoints, stale
  response guards, and corrected follower integration docs. Done in
  `checkpoints/2026-06-06-phase-4-typed-following-status.md`.
- PXE-0047: typed process-local following telemetry now has
  `GET /api/v1/following/telemetry`, live setpoint fields with a declared
  `field_source`, optional command intent/target-loss/safety/performance
  diagnostics, circuit-breaker status, command-publication summary, structured
  `/api/v1` errors, dashboard `useFollowingTelemetry()` adoption through the
  endpoint registry, legacy fallback for missing typed endpoints, stale response
  guards, and updated API/follower docs. Done in
  `checkpoints/2026-06-06-phase-4-typed-following-telemetry.md`.
- PXE-0048: the Follower visualization page now consumes typed
  `GET /api/v1/following/telemetry` for follower/setpoint history snapshots
  through the endpoint registry, falls back to legacy follower telemetry only
  when the typed route is missing, normalizes typed/legacy field maps into
  chart-compatible aliases, bounds history/log growth, performs an initial
  refresh, and ignores stale out-of-order responses. The companion tracker plot
  migration is closed under PXE-0049. Done in
  `checkpoints/2026-06-06-phase-4-follower-page-typed-telemetry-history.md`.
- PXE-0049: typed process-local tracker telemetry now has
  `GET /api/v1/tracking/telemetry`, live `TrackerOutput` geometry/field
  snapshots with a declared `field_source`, embedded runtime status,
  compatibility fallback to legacy tracker telemetry, structured `/api/v1`
  errors, dashboard Follower visualization tracker-plot adoption through the
  endpoint registry, fallback only for missing typed routes, timestamp
  normalization, stale response guards, and updated API/follower docs. Done in
  `checkpoints/2026-06-06-phase-4-typed-tracker-telemetry-history.md`.

Objective:

- Keep the maintained official `px4io/px4-sitl-gazebo:<tag>` visual validation
  path operator-gated and record exact host/image evidence. On this VPS, the
  selected official image starts Gazebo but PX4 times out waiting for world
  readiness; full L4 acceptance needs a native GUI/better runner or a separately
  proven official-image startup workaround.
- Prove PixEagle ingests simulated Gazebo RTP/H.264 video through the same
  UDP/GStreamer receiver contract already proven with generated video.
- Package scenario-specific visual evidence with PixEagle video/tracker/follower
  traces, command traces, route/profile snapshots, config snapshots, PX4 logs,
  params, ULog/tlog where available, and exact image/tag/digest metadata.
- Keep claim boundaries strict: Gazebo visual SITL is simulation evidence only
  and cannot imply HIL, field, or real-aircraft success.

Acceptance:

- Generated RTP/UDP receiver proof remains green before any Gazebo camera
  evidence is accepted.
- Official Gazebo image can run headless on the selected validation host or the
  inability is recorded with exact command, tag, image, and missing capability.
- PixEagle ingests simulated video through the documented UDP/GStreamer path and
  produces tracker/follower/command artifacts without field claims.
- PX4 params, logs, ULog/tlog availability, route/profile evidence, config
  snapshots, and image metadata are captured or the run is incomplete.
- Normal PR CI remains free of external PX4/Gazebo runtime requirements until
  the profile has proven stable as an opt-in/nightly gate.

Current host boundary:

- Rechecked on 2026-06-04: Docker is installed (`29.1.3`). The current shell
  still lacks the `docker` group, but `sg docker -c 'docker ps ...'` works
  because `alireza` is now in `/etc/group`.
- `px4io/px4-sitl:v1.17.0` is not a valid Docker Hub tag. The active SIH
  profile now uses `px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01` with repo
  digest `px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865`.
- `px4io/px4-sitl-gazebo:v1.17.0` is not a valid Docker Hub tag. The profile
  now uses `px4io/px4-sitl-gazebo:v1.17.0-alpha1-1551-g381149fb01` with repo
  digest `sha256:fe3608d282e214db19763d63e857b603781c6471fe0bc3276373927bb01f51db`.
- The official image starts Gazebo 8.11.0 and contains `gz_x500_mono_cam`,
  `gz_x500_gimbal`, and the `GstCameraSystem` UDP video plugin. The all-in-one
  PX4/Gazebo entrypoint still timed out waiting for `/world/default/scene/info`
  on this VPS/headless path, so no accepted L4 visual pass is claimed.

## Planned Slices

| Phase | Slice | Main Issues | Goal |
| --- | --- | --- | --- |
| 3 | Official Gazebo visual SITL runtime proof | PXE-0040 | Execute the hardened official Gazebo profile on native Ubuntu GUI/GPU, a stronger headless runner, or a separately proven official-image startup workaround; capture video/tracker/follower/PX4 evidence and keep the manifest incomplete unless artifact and content checks pass. |
| 3 | X-Plane/Windows SITL disposition | PXE-0020 | Rewrite as maintained evidence workflow or move to historical docs. |
| 4 | API/MCP modernization | PXE-0008 | Continue typed `/api/v1` migration beyond the current status/telemetry/action resources: route migration tests, router extraction, command/action durability, curated agent registry/policy design, and FastAPI/OpenAPI client contract tests. Companion sidecar standards were closed under PXE-0022. |
| 4 | API authentication and exposure boundary | PXE-0064 | Replace the current unauthenticated broad-bind posture with an explicit production trust/auth/authorization boundary; protect HTTP, WebSocket, video, and mutation paths; retire immediate legacy mutations; preserve local development ergonomics through explicit profiles. |
| 4 | Bootstrap/setup UX cleanup | PXE-0068 | `demo_lan_browser` credential generation, exact Host/CORS, warning UX, and tests are implemented; keep `production_remote` gated on TLS/operator hardening and adversarial auth/media tests; add backend media WebSocket health reporting; remove any remaining stale setup/service/download contradictions found in later slices. |
| 4 | QGC authenticated remote HTTP/WS media | PXE-0070 | Rebase/repair PR #13594 and add reviewed Authorization/Origin/TLS/redaction/test support before advertising remote PixEagle HTTP/WebSocket media from QGC on a different host. |
| 4 | Dashboard API/client normalization | PXE-0008, PXE-0021 | Continue typed client consolidation beyond telemetry/tracker health, migrate remaining dashboard consumers away from legacy route shapes, and move from CRA to a supported frontend toolchain. |
| 5 | Gimbal provider expansion | PXE-0023 | Add MAVLink Gimbal v2 or vendor-specific providers when selected hardware/protocol evidence is available. |
| 5 | Runtime cleanup and docs parity | PXE-0041, remaining open/new issues | Remove redundant legacy code/docs/config after replacements are proven and publish a final no-legacy readiness report. |

## Pause Resume Checklist

1. Check `git status --short` and current branch.
2. Read this file, the issue register, latest journal entry, and latest
   checkpoint.
3. Refresh companion references before API/devops/docs slices:
   - `/home/alireza/mavlink-anywhere`
   - `/home/alireza/mavsdk_drone_show`
   - `/home/alireza/smart-wifi-manager`
4. Verify active slice and acceptance gates before editing.
5. Do not revert unrelated local changes.
6. At slice end, update journal, checkpoint, issue register, and offline copy in
   `/home/alireza` when the report matters for maintainer review.

## Review Gate

At the end of each slice, run focused tests first, then request independent
review against these roles:

- drone/PX4/MAVSDK safety and GNC
- computer vision, tracker/detector, and YOLO integration
- backend API, MCP, and typed contract design
- frontend operator UI/UX
- DevOps, scripts, Linux companion, and embedded operations
- product/field-operator readiness
- code hygiene and legacy-debt removal

Concerns from the review gate must be fixed or explicitly recorded as tracked
debt before moving to the next slice.
