# PixEagle Modernization Phase And Slice Map

Last updated: 2026-07-21

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
| Phase 5 beta14 guided installer and GStreamer build acceptance recovery | in_progress | PXE-0115, PXE-0116 | `checkpoints/2026-07-21-phase-5-beta14-guided-installer-gstreamer-recovery.md`; beta.13 maintainer evidence isolated discarded yes/no responses and a post-compile Python-bytecode source-digest false positive. Beta.14 repairs both bootstrap readers, makes Core plus only the shell shortcut the guided Enter path, rejects ambiguous optional choices, fails closed on terminal loss, keeps service/auto-start explicit, and suppresses Python bytecode without weakening strict OpenCV source integrity or rollback. Focused/setup/update/docs/Phase-0/schema/dashboard gates pass; exact candidate `a1bce296` clean handoff passed 26/26 and independent review returned GO. `v7.0.0-beta.14` is published and the credential-preserving browser-only bench passed its bounded dashboard/media/auth smoke. Next: maintainer GStreamer rerun on disposable Ubuntu. A reviewed model downloader remains deferred; the pinned manual lab example remains. |
| Phase 5 beta13 profile-driven Python compatibility and Ubuntu 26.04 Full AI proof | done | PXE-0114 | `checkpoints/2026-07-20-phase-5-python314-full-ai-compatibility.md`; replaced the stale global PyTorch/Python gate with schema-validated profile policy, current Linux CPU Python 3.14 support, interactive Core fallback/unattended fail-closed behavior, interpreter-aware venv repair, focused tests, isolated Ubuntu 26.04/Python 3.14 Core/Full AI dependency evidence, and exact candidate `d1a11bf2` clean handoff 26/26. Published as `v7.0.0-beta.13` at final evidence commit `985ecbd3`; maintainer fresh Ubuntu/Raspberry Pi, configured model on the clean host, GStreamer target, PX4/SIH/SITL/HIL, QGC, field, and aircraft gates remain separate. |
| Phase 5 beta6 beginner bootstrap and local follower test | in_progress | PXE-0108 | `checkpoints/2026-07-18-phase-5-beta6-beginner-lab-follower-test.md`; one-line mutable-main/Core onboarding, explicit `make demo` local follower-test profile, fail-closed profile YAML serialization, warning-only diagnostic bypass behavior, and live no-PX4 intent smoke are implemented; release/push and maintainer Ubuntu acceptance remain gates |
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
| Phase 4 dashboard tracker-state clarity | done | PXE-0024 | `checkpoints/2026-06-04-phase-4-dashboard-tracker-state-clarity.md`; dashboard tracker runtime normalization distinguishes output-visible, active, stale, not-usable, no-output, checking, and unavailable states; tracker cards/data display/status chips/nav/follow controls consume the normalized state; legacy and typed Offboard-start paths fail closed on absent/stale/unusable tracker output; at that checkpoint legacy tracker telemetry and current-status handled `MULTI_TARGET` target visibility plus `has_output`, `usable_for_following`, and `data_is_stale`; current-status was later retired by the 2026-07-02 runtime/output alias slice; deeper typed tracker runtime/API/internal cleanup closed under PXE-0044 |
| Phase 4 typed tracker runtime status | done | PXE-0044 | `checkpoints/2026-06-05-phase-4-typed-tracker-runtime-status.md`; shared tracker runtime evaluator, typed `/api/v1/tracking/runtime-status`, legacy tracker/current compatibility fields at that checkpoint, selector/hook migration to typed runtime state, reverse-proxy-safe tracker hooks, and TargetLossHandler fail-closed active+stale/not-usable handling done; public current/current-status aliases were later retired on 2026-07-02 |
| Phase 4 typed runtime status | done | PXE-0045 | `checkpoints/2026-06-05-phase-4-typed-runtime-status.md`; typed `/api/v1/runtime/status`, shared snapshot helper behind legacy `/status`, mode/subsystem separation, fail-closed local following classification for unsafe Offboard commander state, dashboard smart-mode migration with legacy route fallback and stale-response guards, route inventory/frontend/backend tests, and refreshed companion refs done |
| Phase 4 typed following status | done | PXE-0046 | `checkpoints/2026-06-06-phase-4-typed-following-status.md`; typed `/api/v1/following/status`, follower profile and OffboardCommander publication summary, fail-closed following readiness classification, dashboard follower-status hook migration with legacy telemetry fallback and stale-response guards, route inventory/frontend/backend tests, and follower integration docs correction done |
| Phase 4 typed following telemetry | done | PXE-0047 | `checkpoints/2026-06-06-phase-4-typed-following-telemetry.md`; typed `/api/v1/following/telemetry`, live setpoint-field snapshot with compatibility fallback, optional target-loss/safety/performance diagnostics, dashboard detailed follower-card hook migration with stale-response guards, route inventory/frontend/backend tests, and docs/reporting updates done |
| Phase 4 Follower visualization typed telemetry history | done | PXE-0048 | `checkpoints/2026-06-06-phase-4-follower-page-typed-telemetry-history.md`; Follower visualization page now uses endpoint registry plus typed `/api/v1/following/telemetry` for follower/setpoint history snapshots, legacy route fallback only for missing typed routes, chart-compatible field aliases, bounded history/log growth, initial refresh, stale-response guards, and focused frontend tests |
| Phase 4 typed tracker telemetry history | done | PXE-0049 | `checkpoints/2026-06-06-phase-4-typed-tracker-telemetry-history.md`; typed `/api/v1/tracking/telemetry`, live TrackerOutput geometry fields with compatibility fallback, embedded runtime status, Follower visualization tracker plot migration, route inventory/backend/frontend tests, and docs/reporting updates done |
| Phase 4 API/MCP candidate inventory | done | PXE-0050 | `checkpoints/2026-06-06-phase-4-api-tool-candidate-inventory.md`; generated non-callable `/api/v1` candidate inventory, source hash, risk/sensitivity classification, action/SITL read-only promotion blocks, agent-context docs, generator drift gate in CI/phase0-check, and focused candidate tests done; no MCP endpoint, registry, `tools/list`, or callable tool exposure added |
| Phase 4 docs-stage agent registry and policy | done | PXE-0051 | `checkpoints/2026-06-06-phase-4-docs-stage-agent-registry-policy.md`; review-only `agent_tools.yaml` and default-deny `agent_policy.yaml` cover the reviewed typed process-local status/telemetry/media-health GET candidates; generator coverage now detects unsafe registry/policy drift; all tools remain `callable: false`, `mcp_exposure: none`, and unpromoted; no runtime MCP endpoint, executor, `tools/list`, or `tools/call` added |
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
| Phase 4 API auth runtime foundation | done | PXE-0064 partial | `checkpoints/2026-06-13-phase-4-api-auth-runtime-foundation.md`; HTTP/MJPEG route execution and video/WebRTC WebSocket acceptance now pass through route authorization; `local_compat` is same-host socket-only and refuses `Host`/proxy-forwarded local proof; non-loopback API clients use scoped hashed bearer records from an external token file; query-string tokens are rejected; at that checkpoint browser sessions and CSRF were still open, and later browser-session, dashboard client/media, security-audit, Offboard/operator action-only, typed tracking action, and tracking/control alias-retirement slices closed those portions; remaining PXE-0064 work is operator credential/TLS hardening and broader adversarial browser/session/media tests |
| Phase 4 browser-session auth foundation | done | PXE-0064 partial | `checkpoints/2026-06-14-phase-4-browser-session-auth-foundation.md`; `API_AUTH_MODE=browser_session` now loads external PBKDF2-SHA256 user records, exposes typed `/api/v1/auth/session`, `/api/v1/auth/login`, and `/api/v1/auth/logout`, creates HttpOnly cookie sessions, validates session-bound CSRF on browser mutations, throttles failed login attempts, enables credentialed exact-origin CORS only in browser-session mode, keeps auth route bodies outside `FastAPIHandler`, and updates API/MCP candidate provenance with no callable tool exposure; later dashboard auth client/media, security-audit, Offboard/operator action-only, typed tracking action, and tracking/control alias-retirement slices closed the frontend, durable-audit, and dangerous-alias portions; remaining work is TLS/operator credential hardening and broader adversarial tests |
| Phase 4 dashboard auth client/media foundation | done | PXE-0064 partial | `checkpoints/2026-06-14-phase-4-dashboard-auth-client-media.md`; dashboard now has one credential-aware `apiClient` boundary for `fetch`, axios, session CSRF, auth-failure refresh, cookie-session MJPEG/WebSocket/WebRTC construction, and protected blob downloads/playback; app shell has login/logout/session UX; operator controls honor session scopes; source guardrails reject raw production `fetch`, direct axios package imports, direct `new WebSocket`, and protected endpoint `href` bypasses; later security-audit, Offboard/operator action-only, typed tracking action, and tracking/control alias-retirement slices closed the audit-event and dangerous-alias portions; remaining work is TLS/operator credential hardening and broader adversarial browser/session/media tests |
| Phase 4 durable API security-audit foundation | done | PXE-0064 partial | `checkpoints/2026-06-16-phase-4-api-security-audit-foundation.md`; added `src/classes/api_security_audit.py` for sanitized append-only JSONL security events with bounded rotation; HTTP, video WebSocket, WebRTC signaling, login, and logout paths record auth decisions/outcomes without credential material; allowed mutation/security-critical requests fail closed if audit cannot be written; `Streaming.API_SECURITY_AUDIT_*` config and generated schema are aligned; API/MCP candidate provenance includes the audit module; later Offboard/operator action-only, typed tracking action, and tracking/control alias-retirement slices retired or replaced dangerous public command paths; remaining work is TLS/operator credential hardening and broader adversarial browser/session/media tests |
| Phase 4 Offboard/operator action-only alias retirement | done | PXE-0064 partial | `checkpoints/2026-06-16-phase-4-offboard-operator-action-only-retirement.md`; retired public HTTP registration for `/commands/start_offboard_mode`, `/commands/stop_offboard_mode`, and `/commands/cancel_activities`; dashboard endpoint registry and Start/Stop/Abort classification now use only typed `/api/v1/actions/*`; API security policy, route inventory, generated API/MCP candidate inventory, and active docs now record those aliases as retired; internal compatibility executors remain only as implementation details until the lower-level control executor is refactored; no PX4/SITL/HIL/field success claimed |
| Phase 4 typed tracking action foundation | done | PXE-0064 partial | `checkpoints/2026-06-16-phase-4-typed-tracking-actions.md`; typed `/api/v1/actions/tracking-start` and `/api/v1/actions/tracking-stop` action resources added with confirmation, dry-run, required idempotency for confirmed mutations, process-local action records, guarded non-callable API/MCP candidate classification, dashboard ROI start/stop migration, and temporary local-only compatibility aliases for `/commands/start_tracking` and `/commands/stop_tracking` that were later retired by `checkpoints/2026-06-19-phase-4-tracking-control-alias-retirement.md` |
| Phase 4 typed tracking utility actions | done | PXE-0064 partial | `checkpoints/2026-06-17-phase-4-typed-tracking-utility-actions.md`; typed `/api/v1/actions/tracking-redetect`, `/api/v1/actions/segmentation-toggle`, `/api/v1/actions/smart-mode-toggle`, and `/api/v1/actions/smart-click` action resources added with confirmation, dry-run, idempotent replay for confirmed mutations, action records, guarded non-callable API/MCP candidate classification, dashboard redetect/segmentation/smart-mode/smart-click migration, temporary local-only compatibility aliases later retired by `checkpoints/2026-06-19-phase-4-tracking-control-alias-retirement.md`, smart-click no-target failure truthfulness, `actions:execute` dashboard scope gating, and reviewer-approved fixes |
| Phase 4 tracking/control alias retirement | done | PXE-0064 partial | `checkpoints/2026-06-19-phase-4-tracking-control-alias-retirement.md`; retired public HTTP registration and alias handler methods for `/commands/start_tracking`, `/commands/stop_tracking`, `/commands/redetect`, `/commands/toggle_segmentation`, `/commands/toggle_smart_mode`, and `/commands/smart_click`; typed `/api/v1/actions/*` resources remain the only HTTP tracking/control mutation surface, security policy resolves retired aliases as unclassified/denied, route inventory shrank by six POST routes, and active docs now record those aliases as retired |
| Phase 4 browser-session/media adversarial regressions | done | PXE-0064 partial | `checkpoints/2026-06-19-phase-4-browser-session-media-adversarial-tests.md`; added backend adversarial tests proving expired browser-session cookies are anonymous only for public session status and rejected from protected media, logout invalidates sibling tabs with the same cookie, and viewer sessions can read media-health but cannot execute typed tracking actions even with a valid CSRF token |
| Phase 4 dashboard browser-session/media adversarial regressions | done | PXE-0064 partial | `checkpoints/2026-06-19-phase-4-dashboard-browser-session-media-adversarial-tests.md`; added frontend service and React Testing Library coverage proving auth-failure refresh to login-required state, failed silent refresh clears browser-session state, logout sends CSRF and clears local session after an expired-cookie response, JSON/blob helpers dispatch auth-failure while preserving structured errors, HTTP/WebSocket/WebRTC media are blocked without authenticated `media:read`, active WebSockets close on auth loss, 1008 WebSocket closes show sign-in guidance without reconnecting, and HTTP media elements use credentialed loading in browser-session mode |
| Phase 4 QGC video compatibility reconciliation | done | PXE-0067 | `checkpoints/2026-06-17-phase-4-qgc-video-compatibility.md`; reviewed QGroundControl PR #13594 at head `f0a4feba`, restored same-host native QGC WebSocket compatibility without weakening remote/browser Origin or media auth gates, documented the direct HTTP/WS versus GStreamer UDP/RTP QGC matrix, aligned active video docs with current `Streaming`/`GStreamer` keys, added stale-doc guard coverage, and regenerated API/MCP candidate provenance; QGC branch merge/auth-header work remains a separate follow-up and no PX4/SITL/HIL/field or service/deployment action was claimed |
| Phase 4 remote media security policy | done | PXE-0069 | `checkpoints/2026-06-17-phase-4-remote-media-security-policy.md`; clarified normal Pi-to-GCS operation without opening anonymous backend media, added `Streaming.API_ALLOWED_HOSTS` to separate backend Host allowlisting from browser CORS origins, documented local-dev, field-QGC RTP/UDP, remote-browser, remote-native HTTP/WS, and rejected anonymous-LAN profiles, added stale video-query and OSD-key docs guardrails, and recorded QGC authenticated remote HTTP/WS implementation as PXE-0070. PXE-0089 later qualified “rejected anonymous LAN” with one explicit `unsafe_demo_lan_media_only` exception limited to `/video_feed` and `/ws/video_feed`; dashboard/control/API access remains authenticated. No QGC branch mutation, PX4/SITL/HIL/field or service/deployment action was claimed. |
| Phase 4 QGC source-profile and demo policy | done | PXE-0071 | `checkpoints/2026-06-17-phase-4-qgc-source-profile-demo-policy.md`; preserved generic QGC HTTP/HTTPS MJPEG and WebSocket support for non-PixEagle sources, documented PixEagle as a stricter configured source profile rather than QGC core behavior, clarified the PixEagle config contract for generic QGC interop (`API_ALLOWED_HOSTS`, exact host authority, future Authorization/Origin/TLS settings, `media:read`-only video token), clarified that beginner full-dashboard LAN demos should use generated browser-session credentials while anonymous demos must be media-only, posted QGC PR clarification comment `https://github.com/mavlink/qgroundcontrol/pull/13594#issuecomment-4731276373`, and updated PXE-0068/PXE-0070 gates plus docs guardrails; no QGC branch mutation, PX4/SITL/HIL/field or service/deployment action was claimed |
| Phase 4 setup-profile foundation | done | PXE-0068 partial | `checkpoints/2026-06-17-phase-4-setup-profile-foundation.md`; added explicit setup-profile tooling, `local_dev` and `field_qgc_video` profile application, fail-closed defined remote/unsafe profiles, Make targets, QGC UDP/RTP default port `5600` alignment, init/install clean-clone default behavior, deployment-only service opt-in, Windows port fallback, companion/troubleshooting cleanup, legacy telemetry WebSocket labeling, and setup-profile/docs regression guards; PXE-0068 remains open for credential-generating remote profile automation and media/service follow-ups |
| Phase 4 binary download provenance | done | PXE-0068 partial | `checkpoints/2026-06-17-phase-4-binary-download-provenance.md`; added shared MAVSDK Server/MAVLink2REST binary manifest, exact asset pins and SHA-256 digests, Linux/Windows dry-run plan output, checksum verification before install, provenance JSONL, explicit override policy, no fallback tag probing, init verification for existing binaries, docs, CI/Phase 0 guardrails, and reviewer fixes; no binary download/install, service/deployment, PX4/SITL/HIL/field, or runtime claims |
| Phase 4 API/MCP candidate disposition governance | done | PXE-0066 | `checkpoints/2026-06-18-phase-4-api-mcp-candidate-disposition.md`; generated inventory now assigns every `/api/v1` candidate an explicit review disposition with owner/rationale/evidence/next gate; current split is 7 approved-for-review-only process-local status/telemetry/media-health GET candidates, 13 blocked auth/action/audit candidates, and 5 deferred SITL validation-stimulus candidates; policy and registry keep all candidates non-callable, unpromoted, and outside runtime MCP exposure |
| Phase 4 SITL sidecar evidence hardening | done | PXE-0065 | `checkpoints/2026-06-18-phase-4-sitl-sidecar-evidence-hardening.md`; maintained SITL plans now declare MavlinkAnywhere version/capability policy, dry-runs expose the policy, runtime evidence captures installed dashboard version, semantic checks classify unavailable/auth/unsupported/unprepared/prepared routing, accepted evidence requires `prepared_routing`, and secret scanning blocks credential-bearing text artifacts without echoing values; no sidecar mutation or runtime PX4/SITL pass claimed |
| Phase 4 streaming media-health API | done | PXE-0068 partial | `checkpoints/2026-06-18-phase-4-streaming-media-health.md`; added typed `GET /api/v1/streams/media-health` with `media:read` authorization, process-local claim boundary, MJPEG/WebSocket/WebRTC/GStreamer/frame-publisher/quality-engine state, stale-frame degradation, disabled and zero-capacity transport reporting, real `ENABLE_STREAMING` route fail-closed behavior, media-specific agent-candidate sensitivity, docs/tests, and no remote browser/QGC/GCS/PX4/SITL/HIL/field receipt claim |
| Phase 4 dashboard/service media-health adoption | done | PXE-0068 partial | `checkpoints/2026-06-18-phase-4-dashboard-service-media-health.md`; dashboard streaming status/performance widgets now consume typed `/api/v1/streams/media-health` with legacy fallback only for missing-route rolling updates, auth failures remain media-health failures, `pixeagle-service status` adds an auth-safe process-local media-health block with optional explicit `media:read` bearer token file, and docs/tests preserve the no-remote-receipt claim boundary |
| Phase 4 streaming lifecycle cleanup | done | PXE-0068 partial | `checkpoints/2026-06-19-phase-4-streaming-lifecycle-cleanup.md`; stale backend WebSocket streaming clients, including clients that never received a frame, now close through one idempotent cleanup path; FastAPI shutdown closes tracked WebSockets, cancels background tasks, and drains WebRTC peers; AppController shutdown releases GStreamer output; GStreamer release nulls the writer and drains queued frames; focused unit/docs gates preserve process-local media-health claim boundaries |
| Phase 4 LAN/private-overlay browser profile hardening | done | PXE-0072 | `checkpoints/2026-06-19-phase-4-lan-overlay-browser-profile-hardening.md`; clarified that TLS is not domain-only while HTTP LAN/private-overlay browser access is lab-only; hardened `demo_lan_browser` host validation for RFC1918, shared private-overlay/CGNAT, link-local, IPv6 ULA/link-local, malformed URL/IPv6, query/fragment, port, public/documentation/multicast, and zone-identifier cases; documented the two-port browser demo requirement (`3040` dashboard plus authenticated `5077` backend/API media) without weakening production gates; Windows `scripts/run.bat` now mirrors Linux by binding the dashboard on LAN only for `trusted_lan_legacy` plus `browser_session` |
| Phase 4 production remote profile | done | PXE-0068/PXE-0064 partial | `checkpoints/2026-06-20-phase-4-production-remote-profile.md`; `production_remote` now atomically generates PixEagle-side HTTPS/WSS reverse-proxy config with rollback, loopback backend bind, exact TLS Host authority/CORS, `browser_session`, secure cookie, audit enabled, external hashed user file, controlled one-time credential handoff, guarded host/origin/path validation, Makefile wrapper, relative dashboard assets, basename-aware navigation, and Linux/Windows launcher behavior that keeps reverse-proxy profiles loopback; the maintained nginx/firewall/evidence runbook does not claim proxy/service installation, TLS deployment, SITL/HIL/field run, or production handoff evidence |
| Phase 4 production remote browser evidence and media-session revocation | done | PXE-0073 / PXE-0064 partial | `checkpoints/2026-06-20-phase-4-production-remote-browser-e2e.md`; dashboard consumers use the reverse-proxy endpoint registry; active MJPEG/video-WebSocket/WebRTC signaling sessions terminate after browser-session revocation; WebRTC peer IDs/capacity are server-owned and bounded; the manual-only self-signed HTTPS Playwright harness enforces exact authority/path/route-query rules, current-checkout builds, managed Chromium provenance, bounded cleanup, raw/final-upload secret scans, and sanitized uploads; exact clean-revision evidence `20260620T215137Z-5ce38f` passed on commit `bf32df19ec7f1e8855c1ea934cfb50128a0cf4ea`; target nginx/Caddy, trusted certificate, firewall, service ownership, and operator deployment evidence remain PXE-0064/PXE-0068 gates |
| Phase 4 QGC authenticated direct media | partial checkpoint | PXE-0070 / PXE-0068 partial | `checkpoints/2026-06-24-phase-4-qgc-authenticated-direct-media.md`; QGC PR #13594 was rebased/repaired generically for optional Authorization, Origin, strict TLS/custom CA, credential redaction, bounded WebSocket JPEG, and recording policy, while PixEagle gained a guarded `qgc_direct_media` profile that generates `media:read` bearer credentials and keeps the backend loopback behind an external HTTPS/WSS proxy. PR #13594 is draft as of 2026-06-25 because user receiver tests are not complete; the prior Windows x64 setup failure cleared on QGC head `717f083c5`, the VideoSettings fixture-lifetime failure was fixed and passed the unit phase on `b2f6405a4`, and QGC head `b98848b2c` passed the visible PR rollup on 2026-06-26, including Linux release x64/arm64 and `Test + Coverage linux_gcc_64 Debug` run `28184014057`. PXE-0070 remains active until target receiver/proxy evidence exists. No target QGC playback, proxy/TLS/firewall deployment, SITL/HIL/field, or real-aircraft success is claimed. |
| Phase 4 setup/bootstrap preflight cleanup | done | PXE-0068 partial; PXE-0074 prep | `checkpoints/2026-06-26-phase-4-setup-bootstrap-preflight-cleanup.md`; first cleanup pass after the clean-walkthrough preflight: Linux-only guided install wording and macOS fail-fast, Makefile `venv` fallback, `make` prerequisites, manual core-first dependency install, dashboard YAML-to-dotenv conversion, PixEagle-owned-only port cleanup, Python socket readiness fallback when `nc` is absent, and regression tests. No clean temp checkout, service install, deployment, SITL/HIL/field, or real-aircraft success is claimed. |
| Phase 4 init summary precision | done | PXE-0068 partial; PXE-0074 prep | `checkpoints/2026-06-26-phase-4-init-summary-precision.md`; `scripts/init.sh` now records explicit ready/skipped/degraded/manual-follow-up state for Node.js, dashboard dependencies, dashboard `.env`, configuration defaults, and MAVSDK/MAVLink2REST binaries; `install.sh` no longer advertises blanket installation completion before users review non-ready summary items. No clean temp checkout, binary download/install, service install, deployment, SITL/HIL/field, or real-aircraft success is claimed. |
| Phase 4 legacy config defaults-sync boundary | done | PXE-0008 partial | `checkpoints/2026-06-26-phase-4-legacy-config-sync-boundary.md`; legacy `/api/config/defaults-sync*` request model plus report and dry-run plan helpers now live in `src/classes/api_legacy_config_sync.py`; `FastAPIHandler` keeps route wrappers and apply execution/rollback logic, route inventory and security policy are unchanged, and guardrails prevent report/plan semantics from drifting back into the handler. No `/api/v1/config` route, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy model route boundary | done | PXE-0008 partial | `checkpoints/2026-06-26-phase-4-legacy-model-route-boundary.md`; legacy `/api/models/*` and deprecated `/api/yolo/*` route bodies now live in `src/classes/api_legacy_model_routes.py`; `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No `/api/v1/models/*` route, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy config mutation boundary | done | PXE-0008 partial | `checkpoints/2026-06-26-phase-4-legacy-config-mutation-boundary.md`; legacy config parameter/section update, validation, defaults-sync apply, revert, backup restore, and import route bodies now live in `src/classes/api_legacy_config_routes.py`; `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No `/api/v1/config/*` route, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy config read boundary | done | PXE-0008 partial | `checkpoints/2026-06-27-phase-4-legacy-config-read-boundary.md`; legacy config schema/current/default reads, section/category listing, diff/compare, defaults-sync read/plan, backup history, export, search, and audit route bodies now live in `src/classes/api_legacy_config_routes.py`; `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No `/api/v1/config/*` route, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy recording route boundary | done | PXE-0008 partial | `checkpoints/2026-06-27-phase-4-legacy-recording-route-boundary.md`; legacy recording start/pause/resume/stop/status/toggle, recordings list/download/delete, storage status, and include-OSD route bodies now live in `src/classes/api_legacy_recording_routes.py`; `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No `/api/v1/recordings/*` route, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy OSD route boundary | done | PXE-0008 partial | `checkpoints/2026-06-27-phase-4-legacy-osd-route-boundary.md`; legacy OSD status/toggle, preset listing/loading, color-mode switching, and mode status route bodies now live in `src/classes/api_legacy_osd_routes.py`; `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No `/api/v1/osd/*` route, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy GStreamer route boundary | done | PXE-0008 partial | `checkpoints/2026-06-27-phase-4-legacy-gstreamer-route-boundary.md`; legacy GStreamer status and runtime toggle route bodies now live in `src/classes/api_legacy_gstreamer_routes.py`; `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No `/api/v1/streams/gstreamer*` route, alias retirement, MCP exposure, QGC playback, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy follower profile route boundary | done | PXE-0008 partial | `checkpoints/2026-06-28-phase-4-legacy-follower-profile-route-boundary.md`; legacy follower schema, profile list, current profile, switch-profile, configured-mode, setpoints-status, and current-mode route bodies now live in `src/classes/api_legacy_follower_routes.py`; `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No `/api/v1/following/*` or `/api/v1/follower/*` route, follower health/restart/config-manager extraction, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy follower route boundary | done | PXE-0008 partial | `checkpoints/2026-06-28-phase-4-legacy-follower-route-boundary.md`; remaining legacy follower health, restart, and config-manager route bodies now live in `src/classes/api_legacy_follower_routes.py`, completing the current `/api/follower/*` route-body extraction. `FastAPIHandler` keeps route wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No typed `/api/v1/following/*` or `/api/v1/follower/*` promotion, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy safety read route boundary | done | PXE-0008 partial | `checkpoints/2026-06-29-phase-4-legacy-safety-route-boundary.md`; legacy read-only circuit-breaker status/statistics, safety config, follower safety limits, effective-limit summary, and relevant-section route bodies now live in `src/classes/api_legacy_safety_routes.py`; `FastAPIHandler` keeps wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. The follow-up circuit-breaker mutation boundary below closes the route-body move for toggle, safety-bypass, and statistics reset. No typed `/api/v1/safety/*` route, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy circuit-breaker mutation boundary | done | PXE-0008 partial | `checkpoints/2026-06-29-phase-4-legacy-circuit-breaker-mutation-boundary.md`; legacy `POST /api/circuit-breaker/toggle`, `POST /api/circuit-breaker/toggle-safety`, and `POST /api/circuit-breaker/reset-statistics` route bodies now live in `src/classes/api_legacy_safety_routes.py`, preserving process-local `Parameters` mutation semantics, reset-on-enable behavior, safety-bypass effectiveness reporting, statistics reset payloads, and legacy broad 503-to-500 error wrapping. `FastAPIHandler` keeps wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No typed `/api/v1/safety/*` action, idempotency redesign, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy media status route boundary | done | PXE-0008 partial | `checkpoints/2026-06-29-phase-4-legacy-media-status-route-boundary.md`; bounded legacy media observability route bodies for streaming status, streaming stats, and video health now live in `src/classes/api_legacy_media_routes.py`; `FastAPIHandler` keeps wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. `POST /api/video/reconnect`, `GET /video_feed`, and `WS /ws/video_feed` were closed by follow-up boundaries below; WebRTC signaling remains a separate media lifecycle slice. No typed `/api/v1/streams/*` promotion, alias retirement, MCP exposure, QGC playback, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy media reconnect mutation boundary | done | PXE-0008 partial | `checkpoints/2026-06-29-phase-4-legacy-media-reconnect-route-boundary.md`; legacy `POST /api/video/reconnect` route body now lives in `src/classes/api_legacy_media_routes.py`, preserving `force_recovery()`, updated health reporting, success/503/500 status mapping, and legacy wrapper docstrings. `FastAPIHandler` keeps route registration and a one-call wrapper, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. `GET /video_feed` and `WS /ws/video_feed` were closed by follow-up media boundaries; WebRTC signaling remains a separate media lifecycle slice. No typed `/api/v1/streams/*` action promotion, alias retirement, MCP exposure, QGC playback, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy media HTTP route boundary | done | PXE-0008 partial | `checkpoints/2026-06-29-phase-4-legacy-media-http-route-boundary.md`; legacy `GET /video_feed` HTTP MJPEG route body and `SessionBoundStreamingResponse` now live in `src/classes/api_legacy_media_routes.py`, preserving streaming-disabled and max-connection failures, adaptive-quality frame encoding, session-revocation termination, cleanup/unregister behavior, and legacy wrapper docstrings. `FastAPIHandler` keeps route registration and a one-call wrapper, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. `WS /ws/video_feed` was closed by the follow-up WebSocket boundary below; WebRTC signaling remains a separate media lifecycle slice. No typed `/api/v1/streams/*` promotion, alias retirement, MCP exposure, QGC playback, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy media WebSocket route boundary | done | PXE-0008 partial | `checkpoints/2026-06-29-phase-4-legacy-media-websocket-route-boundary.md`; legacy `WS /ws/video_feed` route body and `ClientConnection` state now live in `src/classes/api_legacy_media_routes.py`, preserving streaming-disabled, Host/Origin, authorization, audit-failure, accept-then-capacity, client registration, task orchestration, session-revocation, and cleanup behavior while leaving shared send/receive/session/heartbeat/shutdown helpers in `FastAPIHandler`. Added direct production-helper tests for JSON metadata plus binary JPEG delivery, quality/ping handling, and exact three-error drop accounting, fixing the prior WebSocket drop overcount. The follow-up WebRTC signaling boundary below closes the remaining media signaling route-body ownership record. No typed `/api/v1/streams/*` promotion, alias retirement, MCP exposure, QGC playback, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy WebRTC signaling boundary | done | PXE-0008 partial | `checkpoints/2026-06-29-phase-4-legacy-webrtc-signaling-boundary.md`; confirmed and guarded that legacy `WS /ws/webrtc_signaling` is registered directly to `WebRTCManager.signaling_handler`, with signaling state, pre-accept streaming/Host/Origin/auth/audit gates, accept-then-capacity behavior, server-owned peer IDs, SDP/ICE handling, browser-session revocation, bounded peer cleanup, and shutdown cleanup owned by `src/classes/webrtc_manager.py`. Generated candidate provenance now hashes the manager, static route-inventory guardrails prevent signaling body drift back into `FastAPIHandler`, and a focused path test covers disabled-audit media-read behavior through the existing accept-then-capacity gate. No typed `/api/v1/streams/*` promotion, alias retirement, MCP exposure, WebRTC receipt claim, QGC playback, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy tracker selector route boundary | done | PXE-0008 partial | `checkpoints/2026-06-30-phase-4-legacy-tracker-selector-route-boundary.md`; legacy tracker available/current/switch/restart/current-config route bodies now live in `src/classes/api_legacy_tracker_routes.py`, preserving schema-manager lookups, runtime-status embedding, raw request JSON parsing, 400/429/500 legacy response shapes, rate-limit bucket semantics, config reload, and AppController switch delegation. `FastAPIHandler` keeps wrappers and route registration, route inventory/security policy are unchanged, generated candidate provenance hashes the helper, and the set-type/available-types follow-up named by this checkpoint was closed by the next row. No typed `/api/v1/tracking/*` promotion, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy tracker set-type route boundary | done | PXE-0008 partial | `checkpoints/2026-06-30-phase-4-legacy-tracker-set-type-route-boundary.md`; legacy `GET /api/tracker/available-types` and deprecated `POST /api/tracker/set-type` route bodies now live in `src/classes/api_legacy_tracker_routes.py`, preserving the hardcoded capability payload, `AI_AVAILABLE` availability reporting, direct legacy AppController `smart_mode_active` and `current_tracker_type` mutations, deprecated response envelope, and legacy 400/500 shapes. `FastAPIHandler` keeps wrappers and route registration, route inventory/security policy are unchanged, and generated candidate provenance hashes the helper. No typed `/api/v1/tracking/*` promotion, alias retirement, MCP exposure, PX4/SITL/HIL/field, or real-aircraft behavior is claimed. |
| Phase 4 legacy tracker diagnostics route boundary | done | PXE-0008 partial | `checkpoints/2026-06-30-phase-4-legacy-tracker-diagnostics-route-boundary.md`; legacy `GET /api/tracker/schema`, `GET /api/tracker/current-status`, `GET /api/tracker/output`, and `GET /api/tracker/capabilities` route bodies moved into `src/classes/api_legacy_tracker_routes.py`, along with current-status field formatting. The move preserved raw schema-file reads, structured output metadata, capabilities fallbacks, current-status runtime flags, raw gimbal/status field shaping, optional smart-tracker inference handling, and legacy broad 500 wrapping. `FastAPIHandler` kept wrappers and route registration, route inventory/security policy were unchanged, and generated candidate provenance hashed the helper. The public current-status/output aliases were later retired by the 2026-07-02 runtime/output alias slice. No typed `/api/v1/tracking/*` promotion, MCP exposure, dashboard migration, PX4/SITL/HIL/field, or real-aircraft behavior is claimed for that checkpoint. |
| Phase 4 typed tracker catalog | done | PXE-0008 partial | `checkpoints/2026-06-30-phase-4-typed-tracker-catalog.md`; typed `GET /api/v1/tracking/catalog` now exposes process-local tracker catalog/configuration metadata with schema-manager UI entries, built-in compatibility tracker types, configured/active tracker identity, embedded runtime status, structured errors, typed error-envelope coverage, and an explicit claim boundary. The route is classified as a control read, appears in the generated candidate inventory as blocked/unregistered/non-callable, and does not change legacy dashboard consumers or retire legacy tracker routes. No MCP promotion, PX4/SITL/HIL/field, follower-response, QGC media validation, service/deployment action, or real-aircraft behavior is claimed. |
| Phase 4 dashboard typed tracker catalog adoption | done | PXE-0008 partial | `checkpoints/2026-06-30-phase-4-dashboard-typed-tracker-catalog.md`; dashboard endpoint registry and tracker schema hooks began preferring typed `GET /api/v1/tracking/catalog` for tracker selector/status catalog and current-config metadata, normalized the typed response into existing component shapes, and, at that checkpoint only, kept legacy `/api/tracker/available`, `/api/tracker/current`, `/api/tracker/available-types`, and `/api/tracker/current-config` as compatibility fallbacks when the typed route was missing or explicitly unsupported. Those catalog/config fallbacks and public aliases were later retired by the 2026-07-02 tracker catalog/config alias slice. Tracker restart/configuration mutations remained legacy pending typed action design at that checkpoint; tracker switch was closed by the 2026-07-01 typed tracker-switch slice below. No backend route changes, MCP promotion, alias retirement, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed for that checkpoint. |
| Phase 4 typed tracker switch action | done | PXE-0008 partial | `checkpoints/2026-07-01-phase-4-typed-tracker-switch-action.md`; typed `POST /api/v1/actions/tracker-switch` now provides dry-run validation, confirmation/idempotency preconditions, process-local action records, schema-manager tracker validation, local configured-state verification, structured errors, security-critical action policy, dashboard endpoint adoption, and legacy `/api/tracker/switch` fallback only when the typed action is missing or unsupported. The generated candidate is blocked/unregistered/non-callable. Tracker restart was closed by the typed tracker-restart slice below; tracker configuration mutation, fallback telemetry/deprecation tracking, and compatibility retirement remain open. No tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 typed tracker restart action | done | PXE-0008 partial | `checkpoints/2026-07-01-phase-4-typed-tracker-restart-action.md`; typed `POST /api/v1/actions/tracker-restart` now provides dry-run validation, confirmation/idempotency preconditions, process-local action records, schema-manager validation for the configured tracker, structured errors, security-critical action policy, dashboard endpoint-registry coverage, and a generated blocked/unregistered/non-callable candidate. At that checkpoint legacy `/api/tracker/restart` remained registered for compatibility; the later restart-alias slice retired it. Broader tracker configuration mutation, fallback telemetry/deprecation tracking, and compatibility retirement remain open. No tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 dashboard tracker compatibility fallback telemetry | done | PXE-0008 partial | `checkpoints/2026-07-01-phase-4-dashboard-tracker-compatibility-fallback-telemetry.md`; dashboard typed tracker catalog/current/available and tracker-switch fallbacks emitted structured client-side `pixeagle:tracker-compatibility-fallback` events, retained the last 50 events in memory for diagnostics, and fell back only for missing or explicitly unsupported typed routes. That telemetry was checkpoint-local for still-registered aliases: tracker switch, catalog, current, available, and current-config fallback branches were removed as their public legacy aliases were retired on 2026-07-02. Auth, policy, and malformed typed payload failures did not fall back. Deprecated `/api/tracker/set-type` was documented as compatibility-only rather than a new-client path. No backend route changes, server-side deprecation counters, alias retirement, runtime tracker success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed for that checkpoint. |
| Phase 4 backend tracker compatibility deprecation counters | done/superseded | PXE-0008 partial | `checkpoints/2026-07-02-phase-4-backend-tracker-compatibility-deprecation-counters.md`; legacy `/api/tracker/*` compatibility route handlers recorded process-local attempted route usage with replacement-path metadata, deprecated `set-type` marking, and a claim boundary at that checkpoint. The July 3 schema/capabilities retirement removed the final public tracker diagnostics and the counter surface itself, so typed `GET /api/v1/tracking/catalog` no longer embeds `legacy_compatibility`. No route inventory change, alias retirement, durable audit log, tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed for the original checkpoint. |
| Phase 4 retired tracker set-type alias | done | PXE-0008 partial | `checkpoints/2026-07-02-phase-4-retire-tracker-set-type-alias.md`; public `POST /api/tracker/set-type` route registration, handler wrapper, direct legacy state-mutating helper, dashboard endpoint constant, security classification, route inventory entry, and active compatibility counter metadata were removed. New clients use typed `POST /api/v1/actions/tracker-switch`; at that checkpoint rolling legacy clients kept `/api/tracker/switch` as the only tracker-selection compatibility fallback. That fallback was retired by the following switch-alias slice. No typed config mutation redesign, remaining alias retirement, tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 retired tracker switch alias | done | PXE-0008 partial | `checkpoints/2026-07-02-phase-4-retire-tracker-switch-alias.md`; public `POST /api/tracker/switch` route registration, handler wrapper/import, request-parsing compatibility helper, dashboard endpoint constant, dashboard fallback path, security classification, route inventory entry, and active compatibility counter metadata were removed. Typed `POST /api/v1/actions/tracker-switch` remains the only first-party tracker-selection mutation path and still uses the internal `switch_tracker_to_type()` executor. No typed config mutation redesign, remaining alias retirement, tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 retired tracker restart alias | done | PXE-0008 partial | `checkpoints/2026-07-02-phase-4-retire-tracker-restart-alias.md`; public `POST /api/tracker/restart` route registration, handler wrapper, dashboard legacy endpoint constant, hidden config badge restart URL, security classification, route inventory entry, and active compatibility counter metadata were removed. Typed `POST /api/v1/actions/tracker-restart` remains the first-party tracker restart/config-reload mutation path and still uses the internal `restart_tracker()` helper. No typed config mutation redesign, remaining catalog/config/diagnostic alias retirement, tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 retired tracker catalog/config aliases | done | PXE-0008 partial | `checkpoints/2026-07-02-phase-4-retire-tracker-catalog-config-aliases.md`; public `GET /api/tracker/available`, `GET /api/tracker/current`, `GET /api/tracker/available-types`, and `GET /api/tracker/current-config` route registrations, handler wrappers/imports, obsolete helper bodies/tests, dashboard endpoint constants and fallback branches, reverse-proxy e2e allowlist entries, security classifications, route inventory entries, and active compatibility counter metadata were removed. Dashboard selector/current/config metadata now requires typed `GET /api/v1/tracking/catalog`; missing or unsupported typed catalog responses surface as operator-visible errors. No typed config mutation redesign, remaining diagnostic alias retirement, tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 retired tracker runtime/output aliases | done | PXE-0008 partial | `checkpoints/2026-07-02-phase-4-retire-tracker-runtime-output-aliases.md`; public `GET /api/tracker/current-status` and `GET /api/tracker/output` route registrations, handler wrappers/imports, obsolete field-shaping helpers/tests, dashboard endpoint constants, reverse-proxy e2e allowlist entries, security classifications, route inventory entries, and active compatibility counter metadata were removed. Dashboard tracker status/output views now consume typed `GET /api/v1/tracking/telemetry` without legacy fallback, while typed `/api/v1/tracking/runtime-status` remains the runtime-read contract. At that checkpoint, schema/capabilities were the only remaining public tracker diagnostics; the July 3 schema/capabilities slice below later retired them. No typed config mutation redesign, tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 retired tracker schema/capabilities aliases | done | PXE-0008 partial | `checkpoints/2026-07-03-phase-4-retire-tracker-schema-capabilities-aliases.md`; public `GET /api/tracker/schema` and `GET /api/tracker/capabilities` route registrations, handler wrappers/imports, obsolete helper bodies/tests, dashboard endpoint constants, reverse-proxy e2e allowlist entries, security classifications, route inventory entries, active compatibility counter metadata, and the obsolete tracker legacy counter contract were removed. Typed `GET /api/v1/tracking/catalog` now carries `data_type_schemas`; dashboard tracker schema metadata reads use the typed catalog without legacy fallback; and the typed catalog no longer carries `legacy_compatibility` because no public legacy tracker diagnostic route remains. No typed config mutation redesign, tracker runtime success, MCP promotion, PX4/SITL/HIL/field, QGC media validation, deployment, or real-aircraft behavior is claimed. |
| Phase 4 VPS/browser test readiness estimate | done | PXE-0068, PXE-0074 | `checkpoints/2026-07-03-phase-4-vps-browser-test-readiness-estimate.md`; current branch readiness was reviewed after tracker alias retirement and split into three lanes: controlled VPS/browser smoke via SSH/private overlay or lab profile, public HTTPS/WSS production remote browser test, and tester/funder handoff. The estimate says the first controlled browser review likely needs 2 focused slices, 3 if host/package/port blockers appear; public production remote adds about 2 to 5 slices depending on TLS/proxy/firewall readiness; browser/operator handoff without PX4/SITL claims is about 4 to 7 focused slices after the controlled smoke. No service start, remote exposure, credential generation, PX4/SITL/HIL/field, QGC playback, or real-aircraft behavior is claimed. |
| Phase 4 clean VPS/browser readiness walkthrough | done | PXE-0068, PXE-0074 | `checkpoints/2026-07-03-phase-4-clean-vps-browser-readiness-walkthrough.md`; clean temp checkout on the VPS at commit `03927605` passed Core init, setup-profile dry-runs, binary dry-run, schema check, minimum backend/API tests, dashboard tests/build, and a local-only backend/dashboard smoke with MAVLink2REST and MAVSDK Server intentionally skipped. The walkthrough fixed the missing shared shell helper, root-scoped the `lib/` ignore rule, hardened direct dashboard startup so it refuses to kill unknown port owners, suppressed npm install audit/fund noise, primed dashboard dependency cache from init, and lengthened service-specific readiness waits. No public browser handoff, credential handoff, MAVSDK/MAVLink2REST runtime proof, PX4/SITL/HIL/field, QGC playback, deployment, or real-aircraft behavior is claimed. First controlled user browser test is now about one focused handoff slice away if SSH/local-only or private-overlay access is acceptable. |
| Phase 4 demo LAN browser VPS handoff | done/pending user test | PXE-0068, PXE-0074 | `checkpoints/2026-07-04-phase-4-demo-lan-browser-vps-handoff.md`; applied `demo_lan_browser` to the private-overlay `wt0` address `100.82.207.49`, generated browser-session credentials with plaintext only in an owner-readable local handoff file, fixed `.venv`/`venv` launcher fallback, repaired the local `.venv` OpenCV contrib package, started backend/dashboard with `bash scripts/run.sh --no-attach -m -k`, and verified dashboard static response, pre-login API denial, authenticated API reads, and headless Chromium login to `/dashboard`. The `pixeagle` tmux session is intentionally left running for user testing. No public HTTP, production HTTPS/WSS, MAVSDK/MAVLink2REST runtime proof, PX4/SITL/HIL/field, QGC playback, deployment, or real-aircraft behavior is claimed. |
| Phase 4 dashboard operator UX cleanup | done | PXE-0076 | `checkpoints/2026-07-04-phase-4-dashboard-operator-ux.md`; Settings mobile section navigation, Tracker Data, Follower Data, shared operator formatting, responsive shell/header/footer/profile selector, chart containers, and diagnostics presentation were cleaned up after user demo feedback. Focused dashboard tests, production build, minimal public demo restart, and authenticated Playwright screenshots for `/settings`, `/tracker`, and `/follower` at mobile/tablet/desktop passed with no horizontal overflow. No PX4/SITL/HIL/field, QGC playback, MAVSDK/MAVLink2REST routing proof, deployment, or real-aircraft behavior is claimed. |
| Phase 4 demo feedback fixes | done/pending user retest | PXE-0077 | `checkpoints/2026-07-04-phase-4-demo-feedback-fixes.md`; second-round public demo feedback fixed canonical tracker-switch action names, stable Tracker/Follower polling indicators, generated video-source dropdown options, Settings Manual-save gating for schema-backed controls, and manual WebRTC public-HTTP guidance. Backend/schema tests, dashboard focused tests, schema check, production build, whitespace check, independent reviewer closure, and live public browser/API smoke passed. No PX4/SITL/HIL/field, QGC playback, MAVSDK/MAVLink2REST routing proof, deployment hardening, or real-aircraft behavior is claimed. |
| Phase 4 runtime logging foundation | done | PXE-0079 | `checkpoints/2026-07-04-phase-4-runtime-logging-foundation.md`, `checkpoints/2026-07-05-phase-4-runtime-logging-pane-capture.md`, `checkpoints/2026-07-05-phase-4-runtime-logging-frontend-ingestion.md`, `checkpoints/2026-07-05-phase-4-runtime-logging-evidence-export.md`, `checkpoints/2026-07-05-phase-4-runtime-logging-live-tail.md`, and the PXE-0074 clean setup walkthrough; PixEagle now creates per-run runtime manifests and `components/backend.jsonl`, redacts common credentials, applies bounded retention, exports a shared launcher run ID, captures `scripts/run.sh` launcher-piped output for started dashboard/sidecar components, exposes read-only typed `/api/v1/logs/status`, `/api/v1/logs/sessions`, `/api/v1/logs/sessions/{run_id}`, and `/api/v1/logs/sessions/{run_id}/export`, adds a dashboard Logs page for operator/debug visibility, export, and bounded Live tail polling, captures authenticated bounded browser errors into `components/frontend.jsonl` through write-only `runtime:report` plus CSRF, and now has clean setup/update evidence. Runtime logs are process-local evidence only, not PX4/SITL/HIL/field proof. |
| Phase 4 optional setup runtime readiness | done | PXE-0080 | `checkpoints/2026-07-05-phase-4-optional-setup-runtime-readiness.md`; optional setup helpers now resolve `PIXEAGLE_VENV_DIR`, `.venv/`, then `venv/`; AI, PyTorch, AI-deps, OpenCV-GStreamer, dlib, and reset-config helpers no longer pin legacy `venv/`; `check-ai-runtime.sh` reports AI/dlib/OpenCV contrib/GStreamer readiness; docs and focused resolver tests were added. On this VPS, OpenCV 4.13.0 with CSRT/KCF and FFMPEG is present, OpenCV GStreamer is `NO`, and torch/YOLO/dlib/NCNN/pnnx are not installed. |
| Phase 4 browser user management CLI | done | PXE-0081 | `checkpoints/2026-07-05-phase-4-browser-user-management-cli.md`; offline `scripts/setup/manage-browser-users.py` provides list/verify/add/set-password/set-role/enable/disable/remove for external browser-session user files, owner-only atomic writes/backups, generated one-time handoff files, tests, and demo/production break-glass docs. |
| Phase 4 browser account API and dashboard administration | done | PXE-0101 | Typed CSRF-protected self-password and admin-user routes now use the canonical owner-only atomic store, durable authorization audit, last-admin/self-mutation guards, target-session revocation, and credential-redacted contracts. The dashboard account chip exposes self-password management to every browser user and responsive user administration to admins; host CLI recovery remains the offline break-glass path. Generated API candidates remain blocked and non-callable. |
| Phase 4 OSD/video overlay polish | done | PXE-0082 | `checkpoints/2026-07-05-phase-4-osd-video-overlay-polish.md`; overlay labels now say `Tracker: Classic`/`Tracker: AI`, stream protocol badges always render visible text, OSD preset/color catalogs are sanitized with blank/unknown fallback behavior, and focused dashboard tests plus production build passed. |
| Phase 4 runtime log bundle UX | done | PXE-0083 | `checkpoints/2026-07-05-phase-4-log-bundle-export-ux.md`; Logs page export now displays filename, run ID, size, SHA-256, claim boundary, and download time, and CORS exposes the corresponding export metadata headers. |
| Phase 4 typed system/about status | done | PXE-0084 | `checkpoints/2026-07-06-phase-4-typed-system-about-status.md`; typed read-only `GET /api/v1/system/about` exposes version/repository/local git/backend/runtime/update-placeholder metadata under `system:read`, dashboard About consumes it with legacy fallback only for missing typed routes, generated API/MCP candidate inventory records it as non-callable review-only, and docs preserve that About does not fetch/pull/restart or prove update availability. |
| Phase 5 SIH Dev/Training validation surface | done | PXE-0085 | `checkpoints/2026-07-07-phase-5-sih-dev-training-validation-surface.md`; typed read-only `GET /api/v1/sitl/status` exposes checked-in SIH plan metadata, latest local manifest summary, command guidance, and strict L2 claim boundaries under `debug:read`; dashboard Validation page shows commands/evidence without browser start buttons or raw injection controls; generated API/MCP inventory blocks the route from read-only promotion. |
| Phase 4 QGC Windows artifact and receiver handoff | done/pending receiver test | PXE-0070 partial | `checkpoints/2026-07-08-phase-4-qgc-windows-artifact-receiver-handoff.md`; run `28971178285` passed build, installer creation, clean install, 28 bundled GStreamer plugins, and upload for unchanged PR head `b98848b2c`, but independent review found its PATH cleanup did not prove verification without the build GStreamer SDK. Corrective run `28993788648` failed the new guard after GitHub re-injected the SDK between steps; fork commit `0952f43f2` moved installed verification into one sanitized PowerShell process and run `28998523729` passed the corrected package-verification gate. Corrected artifact `8191101989` was downloaded with SHA-256 `686b8fc07d8fabd0a64d59794ec554e3a4c27ccec9bc97cc599e7f48852479ef`, fork commit `1fb98c85d` removed the temporary workflow again, and `tools/qgc_media_test_source.py` now provides a lab-only generated MJPEG/WebSocket JPEG source for self-contained receiver tests. PR remains draft; no QGC receiver playback or remote PixEagle interoperability success is claimed until the remaining receiver/proxy gates pass. |
| Phase 4 tracker identifier normalization | done | PXE-0008 partial | `checkpoints/2026-07-09-phase-4-tracker-identifier-normalization.md`; typed tracker catalog entries now expose `request_tracker_type` plus `factory_key`, schema-manager resolution accepts both schema keys and existing config factory keys (`CSRT`, `KCF`, `dlib`, `Gimbal`), AppController stores canonical schema keys after successful switches, dashboard selector sends the catalog request identifier, and regression tests cover factory-key restart/default and factory-key switch normalization. Broader typed tracker configuration mutation remains the next PXE-0008 slice. |
| Phase 4 QGC lab source receiver correction | done | PXE-0087 | `checkpoints/2026-07-09-phase-4-qgc-lab-source-receiver-fix.md`; the generic lab source now emits changing JPEG frames over HTTP MJPEG and WebSocket JPEG, supports HTTP `HEAD`, provides a browser WebSocket viewer, and documents that VLC consumes MJPEG rather than raw WebSocket URLs. |
| Phase 4 authenticated PixEagle actual-feed bench | done | PXE-0088 | `checkpoints/2026-07-09-phase-4-qgc-actual-feed-bench.md`; owner-only `media:read` credentials proved authorized public-VPS MJPEG and WebSocket JPEG from the actual PixEagle feed while anonymous requests remained denied at that checkpoint. PXE-0089 later added a separate explicit unsafe lab exception. |
| Phase 4 unsafe anonymous media-only lab profile | done | PXE-0089 | `checkpoints/2026-07-09-phase-4-unsafe-anonymous-media-profile.md`; one default-off config flag and explicit setup profile permit anonymous access only to actual-feed `/video_feed` and `/ws/video_feed` for short lab benches while dashboard, control, config, logs, WebRTC, media-health, and other API routes remain authenticated. |
| Phase 4 QGC Host authority/client-IP clarification | done | PXE-0090 | `checkpoints/2026-07-10-phase-4-qgc-host-vs-client-ip-clarification.md`; active docs, setup output, and regressions distinguish URL/proxy Host authority, browser Origin/CORS, network source-IP restriction, and PixEagle authorization. |
| Phase 4 GStreamer output/runtime closure | done | PXE-0091, PXE-0040 partial | `checkpoints/2026-07-12-phase-4-gstreamer-output-runtime-closure.md`; optional QGC/GCS H.264/RTP/UDP output now has validated config, bounded scheduling, independent OSD sizing, serialized encoder generations, retained async-release ownership, typed cleanup health, a transactional OpenCV-GStreamer builder with strict path/removal/rollback gates, runtime capability diagnostics, 228 focused tests, 430 Phase 0 tests, dashboard build/tests, and clean independent review. The VPS OpenCV build still reports GStreamer `NO`; no target UDP receiver or visual/PX4 success is claimed. |
| Phase 4 video-file EOF/replay safety | done | PXE-0092 | `checkpoints/2026-07-13-phase-4-video-file-eof-replay-safety.md`; VIDEO_FILE now has explicit LOOP/STOP EOF policy, ordered probe delivery, verified seek/reopen, replay epoch/provenance, deterministic pacing, and command-freshness/Offboard denial while preserving non-video provider contracts. |
| Phase 4 full-suite harness closure | done | PXE-0093 | `checkpoints/2026-07-13-phase-4-full-suite-test-harness-closure.md`; repaired the extracted WebSocket guard and deterministic recording-overflow test, then passed the complete maintained non-hardware suite. |
| Phase 4 configuration authority and transactional runtime sync | done | PXE-0094 | `checkpoints/2026-07-14-phase-4-config-authority-transactional-runtime-sync.md`; exact schema authority, explicit versioned retirements, extension-preserving sync v2, opaque apply tokens, serialized durable mutations, post-replace write receipts, conditional rollback, coherent runtime generations, model/target/inference barriers, staged Linux/Windows update baselines, `.venv` cleanup, dashboard UX, and docs passed focused, Phase 0, full backend, dashboard, schema, and static gates. Initial independent findings and the local final audit were repaired; the delegated final re-review exhausted separate quota before verdict. The ignored VPS config was not migrated in this slice. |
| Phase 4 public demo and QGC receiver candidate | automated gates done/pending manual receiver test | PXE-0095 | `checkpoints/2026-07-14-phase-4-public-demo-qgc-receiver-candidate.md`; migrated the preserved live config through authenticated exact-plan sync, pinned clean PixEagle run `pixeagle_20260714T132818Z_558897`, passed public auth/MJPEG/WS/Origin/browser/replay probes, promoted generic QGC head `ab5213f4f` to mergeable draft PR #13594 after exact Linux/Windows/macOS/security/docs gates, and exposed a public checksummed Windows AMD64 installer. Manual Windows receiver/reconnect/MKV/MOV acceptance, production TLS, Raspberry Pi setup, cleanup, tag, and release remain open. |
| Phase 4 exact-candidate VPS migration and handoff | automated gate done/pending authenticated maintainer test | PXE-0098 | `checkpoints/2026-07-16-phase-4-exact-candidate-vps-handoff.md`; preserved and hashed ignored operator state, applied all 21 config-sync v2 operations with zero-actionable post-state and unchanged credentials, fixed three live-discovered launcher consistency defects without broad refactoring, passed focused 39/54/150-test gates plus bounded independent `GO`, and launched exact pushed commit `9b1b6f6c` as healthy public run `pixeagle_manual_97590a57-ba07-4781-a99e-5acf76e0d456`. Dashboard/API-denial/MJPEG/WS/Origin/pre-login probes passed; authenticated UI, RPi/target, QGC, production cleanup, tag, and release remain later gates. |
| Phase 5 bootstrap/Full/RPi handoff readiness | automated VPS gate done/pending Raspberry Pi execution | PXE-0074, PXE-0099 | `checkpoints/2026-07-16-phase-5-bootstrap-full-rpi-handoff-readiness.md`; corrected configured telemetry-port ownership, canonical port parsing, first-run AI verifier output isolation, read-only help locking, and portable evidence paths; completed a real Full CPU transaction/runtime smoke; passed 272 focused tests, 72 mandatory tests, schema/static gates, bounded independent `GO`, and exact `6df1cb4e` clean evidence with 26/26 commands plus 49 dashboard suites/296 tests/build. Final candidate `a25b104b` then passed a dashboard-inclusive 26/26 clean-clone refresh with 49 suites/297 tests/build; the updater was explicitly skipped only because its separate run correctly refused the active public demo. The owner-only Core-first RPi guide is present at mode `0600`, and its local command audit closed installer-status, bounded-log, and model-path documentation defects. Raspberry Pi Core/Full execution, model inference, GStreamer, QGC, PX4, production, tag, and release remain separate. |
| Phase 5 VPS operator-feedback and restart closure | automated and authenticated VPS gates done/pending maintainer test | PXE-0100 | `checkpoints/2026-07-16-phase-5-vps-feedback-closure.md`; operator wording, allowed-origin stale-session recovery, current production-browser contracts, and the supervised restart/watchdog exit-code race are closed. Final commit `e4121ce4` passed backend/dashboard/schema/static/security gates and two bounded independent `GO` reviews. Exact run `pixeagle_manual_78362d7d-8d7a-43e1-be2c-04e290181ba8` completed two real dashboard restarts with PIDs `2565651 -> 2566525 -> 2566632`, source restore `test4 -> test3 -> test4`, exact-origin reauthentication, zero page errors, zero pending changes, and unchanged owner-only credentials. Raspberry Pi, AI/model, QGC, PX4-in-loop, production TLS, tag, and release remain separate. |
| Phase 5 VPS basic AI readiness | automated/authenticated VPS and clean-checkout gates done/pending maintainer browser test | PXE-0074, PXE-0104 | `checkpoints/2026-07-17-phase-5-vps-basic-ai-readiness.md`; maintained Full CPU dependencies, publisher-digest-bound YOLO26N, deterministic first inference, SmartTracker output, authenticated model/media/browser checks, setup lessons, canonical runtime-owner guidance, and atomic no-replace local model ingestion passed 407 focused tests/1 skip, 72 mandatory tests, schema/static gates, and two final independent `GO` reviews. Exact clean candidate `56695360` then passed 26/26 handoff commands, 49 dashboard suites/297 tests, production build, source-clean-at-start, and clean initial/final temporary-checkout gates; the updater was skipped only because the public tester runtime remained active. Physical Raspberry Pi Core/Full/model, target tracking quality, PX4/follower, optional NCNN/GStreamer, QGC, production, tag, and release remain separate. |
| Phase 5 follower command preview | automated release/VPS gate done; Ubuntu acceptance pending | PXE-0107 | `checkpoints/2026-07-18-phase-5-command-preview-beta5.md`; explicit default-off `COMMAND_PREVIEW` runs recorded-video tracker/follower math through a bounded local `CommandIntent` recorder, keeps replay rejected for PX4, requires the active circuit breaker and disabled safety bypasses, and exposes typed/dashboard claim boundaries. Backend/API/config 396 passed; dashboard 53 suites/342 tests, lint, build, schema, compile, and diff gates passed; post-fix full backend suite passed 3,361 with 48 expected skips. Beta5 was pushed/tagged, the public VPS run was refreshed, and the authenticated probe observed a finite follower intent with PX4 publication false. Fresh Ubuntu, Raspberry Pi, PX4/SIH/SITL/HIL, QGC, WebRTC ICE/TURN, and field evidence remain separate. |

## Active Slice

Current resume note for 2026-07-18: PXE-0107 adds the explicit
`COMMAND_PREVIEW` replay-to-intent path and has passed its backend/API/config
396-test gate plus dashboard 53-suite/342-test, lint, build, schema, compile,
and diff gates. The default `PX4` path still rejects replay; preview requires
the active circuit breaker and both safety bypasses disabled. Next: commit and
push `v7.0.0-beta.5`, refresh the public browser-only VPS from the exact source,
inspect fresh logs, then provide the clean Ubuntu Core/Full handoff. Public
HTTP WebRTC remains unaccepted; use Auto/WebSocket until PXE-0103 has a reviewed
TURN/ICE path. Managed SIH remains disabled and PX4-only. Do not claim
Raspberry Pi, target tracking quality, PX4/SIH runtime, follower response,
SITL/HIL/field, QGC, or real-aircraft success without corresponding evidence.

Historical resume note for 2026-07-14: PXE-0095 reached manual Windows lab
testing with PixEagle commit `cf16411a`, run
`pixeagle_20260714T132818Z_558897`, and QGC draft head `ab5213f4f`. The current
PixEagle handoff above supersedes its public-run pointer; QGC remains deferred
until PixEagle acceptance.

Historical resume note for 2026-07-12: PXE-0091 is code/test/review complete and
awaits commit/push on the PixEagle modernization branch. Next, commit and push
the independently reviewed generic QGC network-video changes, run exact QGC
CI on that commit, obtain and verify a replacement Windows installer, then
update PR #13594 with force-with-lease while keeping it draft through user
receiver testing. After source and artifacts are pinned, restart the public
PixEagle lab bench from the committed source, preserve the current tester
password, verify HTTP/WebSocket media and auth boundaries, monitor runtime
logs, and publish the tester handoff. Do not claim GStreamer UDP receipt,
Gazebo/PX4/SITL/HIL, field, or real-aircraft success without corresponding
artifacts.

Resume note for 2026-06-26: the PixEagle-side PXE-0070 reporting/code slice is
committed, and QGC PR #13594 head `b98848b2c` has a successful visible PR
rollup, including Linux run `28184014057`. QGC PR #13594 must remain draft
until target receiver/proxy evidence is accepted. The 2026-06-25
setup/bootstrap preflight added concrete PXE-0068/PXE-0074 walkthrough probes
for macOS scope, Python environment naming, prerequisites, manual dotenv
generation, dependency split, setup summaries, port-conflict handling, and
verification strength. After PXE-0070, resume the planned Phase 4 cleanup
order: production/security evidence, setup UX cleanup, API/MCP migration,
dashboard client/toolchain modernization, and validation-roadmap work.
The 2026-06-26 setup/bootstrap cleanup closed the local preflight findings for
macOS scope, venv fallback, prerequisites, manual dotenv conversion, dependency
split, port ownership, hidden `nc`, and init-summary precision. Remaining setup
work is target deployment evidence under PXE-0064/PXE-0068 plus final
release-candidate reruns of the clean walkthrough on the exact release branch.
The 2026-07-03 VPS/browser readiness checkpoint refines the next handoff path:
run a controlled PXE-0074 clean temp-directory walkthrough and browser smoke
first, preferably through SSH/private overlay or the lab browser profile, before
attempting production public HTTPS/WSS evidence. The first user browser test is
estimated at 2 focused slices in the best case, 3 if the VPS has package,
browser, or port blockers. Production remote and tester/funder handoff remain
separate, evidence-backed slices.
The 2026-07-03 clean VPS/browser readiness walkthrough completed the first of
those handoff slices. Clean Core init, setup dry-runs, schema/API/dashboard
gates, and local-only dashboard/backend smoke passed on the VPS, with
MAVLink2REST and MAVSDK Server intentionally skipped. Startup fixes from that
walkthrough are tracked in the checkpoint. The next recommended slice is now a
controlled user browser handoff through SSH/local-only or private-overlay/lab
access, followed by a short evidence report. Public HTTPS/WSS remains separate
PXE-0064/PXE-0068 target deployment evidence work.
The 2026-07-04 demo LAN browser handoff completed that private-overlay browser
slice and left the demo running at `http://100.82.207.49:3040` for user test.
After user confirmation, either record the observed result and stop/rotate demo
credentials, or continue into production remote HTTPS/WSS evidence if public
access is required.
The 2026-07-04 dashboard operator UX cleanup closed PXE-0076 after the user
tested the public quick browser demo and reported Settings/Tracker/Follower
usability defects. The public demo now serves the updated dashboard bundle at
`http://204.168.181.45:3040`, authenticated responsive Playwright evidence for
`/settings`, `/tracker`, and `/follower` passed across mobile/tablet/desktop,
and the temporary public HTTP credential was intentionally kept stable for the
current user test session. Next resume point: collect user retest feedback,
then stop/rotate or delete the temporary public HTTP credential when testing is
done; after that continue public-demo cleanup, production remote evidence, or
final tag dry run based on maintainer priority. The 2026-07-08 PXE-0074
dashboard clean-handoff lane later closed the dashboard clean-clone proof.
The 2026-07-04 demo feedback fix slice closed PXE-0077 after the second public
demo retest found tracker-switch, polling-status, video-source schema, Settings
Manual-save, and manual WebRTC public-HTTP defects. The live demo now validates
canonical tracker catalog names through typed tracker-switch dry-run, exposes
the video-source choices through the generated schema and Settings dropdown,
keeps Tracker/Follower status stable during polling refreshes, and shows manual
WebRTC guidance on public HTTP instead of waiting forever. The demo remains
running at `http://204.168.181.45:3040` for user retest with the same temporary
credential. Next resume point: collect user retest feedback, then stop/rotate
or delete the temporary public HTTP credential and temporary public firewall
rules; after that continue public-demo cleanup, production remote evidence, or
final tag dry run based on maintainer priority. The 2026-07-08 PXE-0074
dashboard clean-handoff lane later closed the dashboard clean-clone proof; QGC
authenticated media validation remains separate PXE-0070 work.
The 2026-07-04 WebRTC/bootstrap/logging audit added PXE-0078 and PXE-0079.
PXE-0078 is the next setup cleanup slice: dependency-role split/gating, stale
dlib path cleanup, one setup matrix, quick-demo side-effect/cleanup summary, and
update-flow clarification. PXE-0079 is the new PixEagle unified runtime logging
track, based on `mavsdk_drone_show` lessons but scoped to PixEagle: runtime
session manifests, component JSONL logs, retention/redaction, typed
`/api/v1/logs/*`, dashboard Logs page, frontend error reports, evidence bundle
export, and bounded live-tail polling. PXE-0079 foundation, launcher-piped
component capture, frontend error ingestion, sanitized evidence export, and
live tail are now implemented; the 2026-07-07 PXE-0074 handoff walkthrough now
covers the clean setup evidence dependency.
The 2026-07-05 user-feedback intake added PXE-0080 through PXE-0086. PXE-0080
is now closed for optional setup helper venv resolution and richer runtime
diagnostics. PXE-0081 is closed for offline browser-session user management and
break-glass reset docs. PXE-0101 now closes the typed account API/dashboard
administration follow-up with atomic persistence, audit, session revocation,
last-admin protection, and responsive UI. PXE-0082 is closed for OSD/video overlay polish in
code, focused dashboard tests, and production build evidence; live public
screenshots remain deferred because no plaintext demo handoff file is present
and the active demo password was not rotated. PXE-0083 is closed for log export
metadata UX and CORS header exposure; offline bundle import/viewer remains a
future typed evidence contract. PXE-0084 is closed for typed read-only
`/api/v1/system/about`, dashboard About adoption, and non-callable docs-stage
agent candidate coverage. PXE-0085 is closed for a typed read-only SIH
Dev/Training validation status route and dashboard Validation page that show
plan/manifest/command metadata without exposing raw injection controls or
claiming PX4/SITL runtime success. PXE-0086 is now closed for the safe
cleanup/update workflow. PXE-0074 now has repeatable clean setup/update
walkthrough evidence plus dashboard-inclusive clean-clone evidence; remaining
handoff work is public-demo cleanup/credential rotation after the active test
session, production target evidence when selected, and final release/tag dry
run. The current public demo password was not rotated during PXE-0080 through
PXE-0086 or the PXE-0074 walkthrough.

The 2026-07-08 PXE-0070 Windows artifact handoff produced a fresh AMD64
installer from unchanged QGC PR head `b98848b2c`. Run `28971178285` passed
build, installer creation, clean install, bundled GStreamer plugin verification,
and upload. Independent review found that its PATH cleanup did not remove the
build GStreamer SDK because slash styles differed, so installed-package runtime
verification is not claimed from that run. Corrective run `28993788648`
failed the new guard after GitHub re-injected the SDK between steps. Fork
commit `0952f43f2` moved installed verification into one sanitized PowerShell
process, and rerun `28998523729` passed the corrected package-verification
gate. The corrected installer is preserved under
`/home/alireza/qgc-pr13594-windows-artifacts/run-28998523729/` with SHA-256
`686b8fc07d8fabd0a64d59794ec554e3a4c27ccec9bc97cc599e7f48852479ef`.
The prior installer remains preserved under
`/home/alireza/qgc-pr13594-windows-artifacts/run-28971178285/` only as
superseded evidence. Fork commit `1fb98c85d` removed the temporary
fork-default-branch artifact workflow again after accepted package evidence was
preserved. PXE-0070 remains active for user Windows playback/recording and
authenticated PixEagle HTTPS/WSS target evidence; PR #13594 remains draft. See
`checkpoints/2026-07-08-phase-4-qgc-windows-artifact-receiver-handoff.md`.

Phase 4 API/MCP modernization. PXE-0042 through PXE-0049 are done for typed
actions, telemetry health, runtime/following/tracker status and telemetry, and
dashboard migration of the touched consumers. PXE-0050 is done for the
generated non-callable API/MCP candidate inventory: all current `/api/v1` HTTP
routes are represented once, only the reviewed typed process-local system/about,
status/telemetry, and media-health GET routes are unpromoted read-only
candidates, and action/SITL routes are blocked from read-only promotion.
PXE-0051 is done for docs-stage
`agent_tools.yaml` and `agent_policy.yaml`: the reviewed candidates are
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
while `FastAPIHandler` keeps one-call read route wrappers. PXE-0061/PXE-0062
record the extraction of the former legacy Offboard/operator execution bodies
before their public HTTP aliases were retired. PXE-0063 is done for typed
`/api/v1/actions/offboard-stop`; dashboard Start Following, Stop Following, and
Cancel Tracker use guarded typed actions, and the former public
`/commands/start_offboard_mode`, `/commands/stop_offboard_mode`, and
`/commands/cancel_activities` routes are no longer registered.
The 2026-06-26 legacy config defaults-sync boundary is done as a PXE-0008
partial: report/plan helpers and the request model moved out of
`FastAPIHandler`, while the legacy route surface and security policy stayed
unchanged. An independent API reviewer recommended the next PXE-0008 slice:
extract legacy `/api/models/*` and `/api/yolo/*` route bodies into an
`api_legacy_model_routes.py` helper without introducing typed model routes or
retiring aliases yet.
The 2026-06-26 legacy model route boundary completed that follow-up:
`/api/models/*` and deprecated `/api/yolo/*` route bodies now delegate through
`api_legacy_model_routes.py`, route inventory/security policy stayed unchanged,
and no typed `/api/v1/models/*` promotion or alias retirement is claimed.
The 2026-06-26 legacy config mutation boundary completed the next queued
PXE-0008 extraction: legacy parameter/section updates, validation,
defaults-sync apply, revert, restore, and import route bodies now delegate
through `api_legacy_config_routes.py`, with route inventory/security policy
unchanged and no typed `/api/v1/config/*` promotion or alias retirement
claimed. The 2026-06-27 legacy config read boundary completed the follow-up:
schema/current/default reads, section/category listing, diff/compare,
defaults-sync read/plan, backup history, export, search, and audit route bodies
also delegate through `api_legacy_config_routes.py`, preserving legacy oddities
such as schema 404 versus missing current/default sections returning `{}`.
The 2026-06-27 legacy recording route boundary completed the next follow-up:
recording start/pause/resume/stop/status/toggle, recordings list/download/
delete, storage status, and include-OSD route bodies now delegate through
`api_legacy_recording_routes.py`, including existing Range download headers and
legacy delete/error mappings. The 2026-06-27 legacy OSD route boundary moved
status/toggle, preset listing/loading, color-mode switching, and mode status
route bodies into
`api_legacy_osd_routes.py`, including existing cache invalidation,
renderer-reinitialization, preset validation, and the legacy unavailable-toggle
500 wrapper. The 2026-06-27 legacy GStreamer route boundary moved status and
runtime toggle route bodies into `api_legacy_gstreamer_routes.py`, including
existing QGC UDP/RTP setup hints, handler creation, direct config flag mutation,
and failed-open 500 response shape. The 2026-06-28 legacy follower profile route
boundary moved schema, profile list, current profile, switch-profile,
configured-mode, setpoints-status, and current-mode route bodies into
`api_legacy_follower_routes.py`, preserving the legacy active-versus-configured
profile payloads, profile validation behavior, setpoint-status compatibility
fields, and safety-limit lookup. The 2026-06-28 legacy follower route boundary
then moved the remaining follower health, restart, and config-manager route
bodies into the same helper, preserving health/resource diagnostics, restart
rate-limit and reload behavior, and config-manager response shapes. Current
`/api/follower/*` route-body extraction is complete. The 2026-06-29 legacy
safety read route boundary moved circuit-breaker status/statistics, safety
config, follower safety limits, effective-limit summaries, and relevant-section
route bodies into `api_legacy_safety_routes.py`, preserving SafetyManager
fallback behavior, rate-unit conversion, and legacy broad error wrapping. The
2026-06-29 legacy circuit-breaker mutation boundary then moved
`POST /api/circuit-breaker/toggle`, `POST /api/circuit-breaker/toggle-safety`,
and `POST /api/circuit-breaker/reset-statistics` into the same helper,
preserving process-local `Parameters` mutation semantics, reset-on-enable
behavior, safety-bypass effectiveness reporting, statistics reset payloads, and
legacy broad 503-to-500 error wrapping.
The 2026-06-29 legacy media status route boundary moved streaming status,
streaming stats, and video health route bodies into
`api_legacy_media_routes.py`, preserving legacy transport counts,
quality-engine state, OSD pipeline stats, video connection health, and OBB
pipeline diagnostics. The 2026-06-29 legacy media reconnect mutation boundary
then moved `POST /api/video/reconnect` into the same helper, preserving
`force_recovery()`, updated health reporting, and success/503/500 mapping while
leaving security policy unchanged. The 2026-06-29 legacy media HTTP route
boundary moved `GET /video_feed` and `SessionBoundStreamingResponse` into the
same helper, preserving MJPEG session revocation and cleanup behavior. The
2026-06-29 legacy media WebSocket boundary moved `WS /ws/video_feed` and
`ClientConnection` into the same helper, preserved pre-accept security,
accept-then-capacity, task orchestration, and session cleanup, and fixed a
WebSocket dropped-frame overcount found by new direct send-loop tests. The
2026-06-29 legacy WebRTC signaling boundary then closed the remaining media
signaling ownership record by guarding direct registration to
`WebRTCManager.signaling_handler`, adding manager provenance, and covering
disabled-audit media-read behavior through the existing accept-then-capacity
gate. The 2026-06-30 legacy tracker selector route boundary then moved
available/current tracker, switch, restart, and current-config route bodies into
`api_legacy_tracker_routes.py`, preserving schema-manager lookups,
runtime-status embedding, rate-limit/reload behavior, and legacy response
shapes. The 2026-06-30 legacy tracker set-type route boundary then moved
`GET /api/tracker/available-types` and deprecated
`POST /api/tracker/set-type` into the same helper, preserving the hardcoded
capability payload, AI availability reporting, deprecation envelope, and direct
legacy AppController state mutation. The 2026-06-30 legacy tracker diagnostics
route boundary then moved schema/current-status/output/capabilities diagnostics
and field formatting into the same helper. The 2026-06-30 typed tracker catalog
slice then added `GET /api/v1/tracking/catalog` as a read-only typed
replacement surface for tracker catalog/configuration metadata, with
schema-manager UI entries, built-in compatibility tracker types, embedded
runtime status, structured errors, security policy coverage, and a generated
candidate that remains blocked/unregistered/non-callable. At that typed catalog
checkpoint, legacy dashboard consumers and legacy tracker routes were
unchanged. The dashboard typed tracker catalog adoption slice then moved
tracker selector/status catalog and
current-config metadata reads to typed `/api/v1/tracking/catalog` with a
then-temporary legacy fallback only for missing or unsupported typed routes.
Those catalog/config fallback branches have now been removed. The 2026-07-01
typed tracker-switch slice added `POST /api/v1/actions/tracker-switch` and
dashboard adoption with a then-temporary legacy fallback only when the typed
action was missing or unsupported; that fallback has also been removed. The
2026-07-01 typed tracker-restart slice added
`POST /api/v1/actions/tracker-restart` with action-resource confirmation,
idempotency, and configured-tracker validation. The dashboard tracker
compatibility fallback telemetry slice then made dashboard legacy fallback
visible with structured `pixeagle:tracker-compatibility-fallback` events and
bounded in-memory event history. The 2026-07-02 backend tracker compatibility
deprecation-counter slice then added process-local attempted legacy route usage
counters to `api_legacy_tracker_routes.py`, embedded them in the typed tracker
catalog as `legacy_compatibility`, and kept typed tracker-restart internal
execution from inflating public legacy route counters. The 2026-07-03 tracker
schema/capabilities retirement then moved schema metadata into typed
`GET /api/v1/tracking/catalog` as `data_type_schemas`, removed the final public
tracker diagnostic aliases, and removed the obsolete tracker legacy counter
contract from the typed catalog and helper module. Remaining PXE-0008 API work
now focuses on typed tracker
configuration mutation design and any future route-boundary debt discovered by
static guards. The public
`POST /api/tracker/set-type` alias was
retired on 2026-07-02 after typed tracker-switch and dashboard migration were
in place. The public `POST /api/tracker/switch` alias was retired later on
2026-07-02 after first-party dashboard fallback to that alias was removed. The
public `POST /api/tracker/restart` alias was retired later on 2026-07-02 after
typed tracker-restart became the only first-party restart/config-reload
mutation path. The public `GET /api/tracker/available`,
`GET /api/tracker/current`, `GET /api/tracker/available-types`, and
`GET /api/tracker/current-config` aliases were retired later on 2026-07-02
after first-party dashboard consumers required typed
`GET /api/v1/tracking/catalog`. The public `GET /api/tracker/current-status`
and `GET /api/tracker/output` aliases were also retired later on 2026-07-02
after dashboard tracker status/output consumers moved to typed
`GET /api/v1/tracking/telemetry`. The public `GET /api/tracker/schema` and
`GET /api/tracker/capabilities` aliases were retired on 2026-07-03 after the
typed tracker catalog carried tracker data-type schemas; no public legacy
tracker diagnostic aliases remain registered.
The 2026-07-01 resume closed the dashboard typed tracker catalog adoption
review loop after fixing the independent malformed-payload blocker with typed
payload validation before dashboard normalization and regression coverage for
`403` and malformed object non-fallback behavior.
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
actions are not registered. Tracking start/stop, redetect, segmentation toggle,
smart-mode toggle, and smart-click are also typed-action-only over HTTP after
the 2026-06-19 tracking/control alias-retirement slice. The 2026-06-19
browser-session/media adversarial regression slice added focused backend
coverage for expired cookies, logout invalidation across tabs, and viewer
media-read/action-denied separation. The dashboard-side adversarial regression
slice added frontend service and component coverage for auth-failure refresh,
failed silent refresh, logout cleanup, structured JSON/blob errors,
HTTP/WebSocket/WebRTC `media:read` gates, active WebSocket close on auth loss,
auth-close operator guidance without reconnecting, and credentialed HTTP media
loading. The 2026-06-19 LAN/private-overlay browser profile hardening slice
clarified that TLS is not domain-only, kept HTTP LAN/private-overlay browser
access lab-only, hardened `demo_lan_browser` host-validation edge cases,
documented the two-port browser demo requirement, and aligned Windows launcher
behavior with Linux for `trusted_lan_legacy` plus `browser_session`. The
2026-06-20 production remote profile slice now atomically generates guarded
PixEagle-side HTTPS/WSS reverse-proxy config, hashed browser-session credentials,
and a controlled one-time handoff while keeping backend/dashboard launchers
loopback. It also adds a maintained nginx/firewall/evidence runbook and makes
the dashboard build/navigation work under `/pixeagle`. PXE-0064 remains open
only for target trusted-certificate/reverse-proxy/firewall/service-account/
audit-path evidence, credential handoff evidence, target-host adversarial
validation, and operator acceptance. PXE-0073 completed the local self-signed
HTTPS/browser application-boundary harness and active media-session revocation
with exact clean-revision evidence on commit `bf32df19`. No runtime MCP
endpoint, executor, `tools/list`, `tools/call`, or callable tool surface exists
from these slices. No runtime PX4/SITL pass is claimed. Official Gazebo runtime
proof (PXE-0040) remains open
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
  action-only and tracking/control alias-retirement slices retired the
  dangerous public command aliases. Remaining PXE-0064 work is operator
  credential/TLS hardening and broader adversarial tests. Done in
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
  Offboard/operator action-only and tracking/control alias-retirement slices
  retired the dangerous public command aliases, and PXE-0073 added local
  clean-revision HTTPS/browser evidence plus active media-session revocation.
  PXE-0064 remains open for target TLS/proxy/firewall/service-account evidence,
  credential handoff, target-host adversarial validation, and operator
  acceptance.
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
  require `usable_for_following=true`, and at that checkpoint legacy tracker
  telemetry plus current-status included targets-only `MULTI_TARGET`
  visibility, `has_output`, `usable_for_following`, and `data_is_stale`.
  First-party dashboard status/output consumers later moved to typed tracker
  runtime/telemetry routes, and current-status was retired on 2026-07-02.
  Done in
  `checkpoints/2026-06-04-phase-4-dashboard-tracker-state-clarity.md`.
- PXE-0044: typed tracker runtime status now has a shared backend evaluator,
  `GET /api/v1/tracking/runtime-status`, compatibility fields that existed on
  `/api/tracker/current` and `/api/tracker/current-status` at that checkpoint,
  dashboard selector and status-hook adoption,
  reverse-proxy-safe tracker hooks, and target-loss fail-closed behavior for
  active+stale or active+not-usable input. Both public runtime aliases were
  later retired on 2026-07-02. Done in
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
| 5 | v7 beta acceptance closure and public refresh | PXE-0105/PXE-0109 done; PXE-0106 in progress; PXE-0074 partial | Beta.9 is published at `81894cde` and exact public run `pixeagle_manual_70f6c1fe-289f-4a48-9c7d-09b59afc131f` is healthy. Dashboard/auth/MJPEG/WebSocket identity checks and the active-retarget Follower Test probe pass with nonzero chase intent, verified hold, fresh post-retarget intent, no PX4 publication, and clean inactive teardown. The clean handoff passed 26/26. Next is maintainer VPS retest, then fresh Ubuntu and physical Raspberry Pi Core/Full/model evidence. Do not imply target GStreamer, production TLS/WebRTC, QGC, PX4/SIH/SITL/HIL, field, or aircraft readiness. |
| 4 | Runtime/setup/model release-candidate hardening | PXE-0096 | Done on pushed candidate `b64d6c28`: local broad/review gates and the 26/26 exact-commit clean-checkout handoff passed. Controlled VPS backup/migration and public operator smoke continue under PXE-0068/PXE-0074 without weakening claim boundaries. |
| 5 | Deferred model internals cleanup | PXE-0097 | Keep nonblocking probe/helper/class-organization cleanup out of the release path; revisit only with behavior-preserving model tests and target Full/RPi evidence. |
| 3 | Official Gazebo visual SITL runtime proof | PXE-0040 | Execute the hardened official Gazebo profile on native Ubuntu GUI/GPU, a stronger headless runner, or a separately proven official-image startup workaround; capture video/tracker/follower/PX4 evidence and keep the manifest incomplete unless artifact and content checks pass. |
| 3 | X-Plane/Windows SITL disposition | PXE-0020 | Rewrite as maintained evidence workflow or move to historical docs. |
| 4 | API/MCP modernization | PXE-0008 | Continue typed `/api/v1` migration beyond the current status/telemetry/action resources: route migration tests, router extraction, command/action durability, curated agent registry/policy design, and FastAPI/OpenAPI client contract tests. Companion sidecar standards were closed under PXE-0022. |
| 4 | API authentication and exposure boundary | PXE-0064 | Collect target trusted-certificate/reverse-proxy/firewall/service-account/audit-path evidence, secure credential-handoff evidence, target-host adversarial browser/session/media results, and operator acceptance. The checked-in local trust/auth/authorization boundary and local clean-revision browser evidence are complete. |
| 4 | Public quick-demo follow-up and credential cleanup | PXE-0068, PXE-0074 | User public-IP test exposed missing UFW handling; `make quick-browser-demo` now records the setup path and public HTTP remains explicit. Keep the current password stable for this active session, then stop the tmux session and rotate/delete the demo credential plus remove temporary public UFW rules when testing is finished. Production remote still requires the HTTPS/WSS evidence path. |
| 4 | Operator dashboard UX and demo retest feedback | PXE-0076, PXE-0077 | Settings, Tracker Data, Follower Data, canonical tracker switching, polling indicators, video-source dropdowns, Settings Manual-save gating, and public-HTTP manual WebRTC guidance are fixed and awaiting user retest on the temporary public demo. After acceptance, stop/rotate/delete the temporary public HTTP credential and firewall exposure, then resume setup/update or production remote evidence work. |
| 4 | Setup/bootstrap UX consolidation | PXE-0078 | Done: Python dependencies are role-based (`requirements-core.txt`, `requirements-ai.txt`, `requirements-dev.txt`), stale optional dlib guidance is fixed, setup docs include a beginner/developer choice matrix, and quick-demo output now previews side effects, skipped sidecars, WebRTC/WebSocket expectations, role, role override, and cleanup. `demo_lan_browser`/`quick-browser-demo` now create an admin first user by default for maintainer bench diagnostics, with `SESSION_ROLE=operator`/`viewer` documented for downgrade. `DRY_RUN=1` is no-touch and custom credential paths no longer chmod existing parent directories such as `/tmp`. Remaining target deployment evidence stays under PXE-0068/PXE-0064; release-candidate reruns stay under PXE-0074. |
| 4 | Optional setup runtime readiness | PXE-0080 | Done: optional setup helpers resolve `PIXEAGLE_VENV_DIR`, `.venv/`, then `venv/`; `check-ai-runtime.sh` reports AI/dlib/OpenCV contrib/GStreamer readiness; focused tests and docs were added. |
| 4 | Unified runtime logging and evidence | PXE-0079 | Done: runtime sessions/manifests, backend JSONL, launcher-captured dashboard/sidecar component output, bounded browser error reports, retention/redaction, launcher run ID, typed read-only `/api/v1/logs/*`, write-only `POST /api/v1/logs/frontend-errors`, `GET /api/v1/logs/sessions/{run_id}/export`, `GET /api/v1/logs/sessions/{run_id}?tail=true`, dashboard Logs page, and PXE-0074 clean setup evidence dependency are complete. Keep security audit separate and do not use runtime logs as flight proof without PX4/SITL/HIL artifacts. |
| 4 | Browser user management and recovery | PXE-0081, PXE-0101 | Done: offline `scripts/setup/manage-browser-users.py` remains the break-glass path; typed CSRF-protected self-password and admin-user APIs, canonical owner-only atomic storage/backups, durable authorization audit, last-admin/self guards, target-session revocation, responsive account/admin UI, redaction tests, and non-callable MCP disposition now close the online management follow-up. |
| 4 | OSD/video overlay polish | PXE-0082 | Done for code/tests/build: explicit `Tracker: Classic`/`Tracker: AI` overlay label, responsive non-empty stream protocol badge, OSD preset/color catalog sanitization, blank fallback, unknown non-empty missing-state display, optional color-mode catalog fallback, and focused dashboard tests. Live public screenshot retest is deferred until tester credential access or explicit demo credential rotation. |
| 4 | Runtime log bundle UX | PXE-0083 | Done for short gate: Logs page displays downloaded export filename, run ID, size, SHA-256, claim boundary, and download time; backend CORS exposes export metadata headers; docs preserve the future import/viewer boundary as a typed evidence contract, not an ad hoc live-runtime import. |
| 4 | Typed About/System status | PXE-0084 | Done: added typed read-only `GET /api/v1/system/about` for version/repository/local git/backend/runtime/update-placeholder metadata, `system:read` security classification, route/candidate inventory coverage, dashboard About dialog adoption with legacy fallback only for missing typed routes, and docs preserving the boundary that runtime About does not fetch/pull/restart or prove update availability. |
| 5 | SIH Dev/Training validation surface | PXE-0085 | Done: typed read-only `GET /api/v1/sitl/status` summarizes the checked-in official-PX4 SIH plan, latest local manifest, and terminal commands under `debug:read`; dashboard Validation shows evidence guidance with strict L2 claim boundaries and no browser execution buttons/raw injection controls; generated API/MCP inventory keeps the route blocked from read-only promotion. |
| 4 | Safe demo cleanup and update workflow | PXE-0086 | Done: added confirmation-gated quick-demo cleanup with dry-run preview, exact credential path/port handoff, default local-only profile restoration, public broad-UFW cleanup matching public setup, CIDR-required LAN/private UFW cleanup, and no-touch backup preservation by default. `make sync`, service sync, and installers now use clean-worktree, fetch, ref verification, and fast-forward-only updates with no auto-stash, hard reset, or merge commit. No live UFW deletion or PowerShell execution was claimed; the follow-on PXE-0074 clean setup/update walkthrough now has repeatable evidence. |
| 4 | Bootstrap/setup UX cleanup | PXE-0068 | `demo_lan_browser`, guarded `production_remote`, launcher handoff, binary provenance, typed media health, lifecycle cleanup, local browser evidence, first setup/bootstrap preflight cleanup, init-summary precision, safe demo cleanup/update flow, and the repeatable PXE-0074 clean setup/update walkthrough are implemented. Remaining setup work is production target proxy/firewall/credential/service evidence and target-host adversarial/operator validation when a deployment target is selected. |
| 4 | QGC authenticated remote HTTP/WS media | PXE-0070, PXE-0095 | PR #13594 now points to exact generic head `ab5213f4f`; Linux receiver/security/lifecycle tests and Windows package verification passed, and a checksummed AMD64 candidate is available. Keep the PR draft through manual HTTP/WS playback, reconnect/source-switch, sustained playback, and playable MKV/MOV evidence. The current anonymous public HTTP/WS lane proves only the explicit unsafe lab profile; authenticated production HTTPS/WSS still needs target certificate/proxy/credential/negative-path evidence. |
| 4 | Dashboard API/client normalization | PXE-0008, PXE-0021 | Continue typed client consolidation beyond telemetry/tracker health, migrate remaining dashboard consumers away from legacy route shapes, and move from CRA to a supported frontend toolchain. |
| 5 | Gimbal provider expansion | PXE-0023 | Add MAVLink Gimbal v2 or vendor-specific providers when selected hardware/protocol evidence is available. |
| 5 | Runtime cleanup and docs parity | PXE-0041, remaining open/new issues | Remove redundant legacy code/docs/config after replacements are proven and publish a final no-legacy readiness report. |
| 5 | Final release/handoff walkthrough | PXE-0074 | Partial pass complete: exact clean candidate `54271cee` passed the dashboard-inclusive 26/26 handoff, and `v7.0.0-beta.9` at `81894cde` is published and running on the public VPS with browser/media/active-retarget/log gates passed. Next, record maintainer beta acceptance, run the one-line public instructions from a fresh Ubuntu host, then capture physical Raspberry Pi Core and Full/model evidence. After the active public test session, remove temporary exposure and rotate/delete demo credentials; production, PX4, QGC, and stable-release gates remain separate. |

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
