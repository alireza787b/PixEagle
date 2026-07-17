# PixEagle Modernization Plan Reconciliation

Date: 2026-06-02  
Repository: `/home/alireza/PixEagle`  
Baseline plan: `audits/2026-04-29-proposed-improvement-plan.md`  
Resume anchors checked: phase map, issue register, 2026-06 journal, checkpoints

## Executive Summary

The first implementation foundation is largely complete. Phase 0 governance,
clean-clone behavior, route inventory, schema/dashboard CI, docs hygiene,
gimbal-provider boundary, command freshness, target-loss fail-closed behavior,
atomic command intents, OffboardCommander ownership, MAVLink request freshness,
PX4/SITL harness scaffolding, and deterministic tracker-in-loop contracts are
done at code/mock-test/docs level.

The project is not yet production-ready. The largest remaining gaps are:

- typed `/api/v1` and MCP-compatible API contracts;
- dashboard API-client/toolchain modernization and stale tracker state UX;
- automated PX4/SITL fault injection and automatic PX4 params/ULog/tlog
  collection;
- production tracker or SmartTracker trace artifacts;
- X-Plane/Windows SITL disposition;
- MAVLink Gimbal v2 or other selected gimbal providers;
- final legacy API/docs/config cleanup after replacements prove parity.

Current issue register status: 29 issues done, 8 open, 1 in progress.

## Original Hard Rules

| Rule | Status | Evidence / Remaining Work |
| --- | --- | --- |
| Flight control owned by a dedicated async service, not the video frame loop | partial | `OffboardCommander` now owns fixed-rate publication and frame-loop direct sends are rejected. A full `FlightControlService` package/state-machine boundary is still not complete. |
| Offboard setpoint heartbeat independent of camera FPS/tracker/UI/streaming | partial | Mock/unit/docs evidence is strong; PX4-in-loop runtime proof remains PXE-0037. |
| Public APIs typed, versioned, route-inventory-tested `/api/v1` contracts | partial | Current legacy route inventory is frozen and API blueprint exists. Typed `/api/v1` routers are still PXE-0008. |
| MCP/AI-agent support from same typed API contracts | open | No MCP surface yet. Depends on PXE-0008 and PXE-0022. |
| Config, schema, docs, dashboard clients, tests, runtime single source of truth | partial | Clean-clone config, schema drift CI, docs guards, test schema drift guard are done. Dashboard client/config API consolidation remains open. |
| Legacy routes/docs/configs only behind tracked deprecation/removal gates | partial | Gimbal legacy docs and removed aliases are handled; legacy API and broader docs/config cleanup remain open. |
| Safety claims backed by tests, SITL scenarios, logs, evidence reports | partial | Unit/mock evidence and SITL harness/action contract exist. Accepted PX4/SITL, HIL, or field evidence has not been produced. |

## Original First Implementation Slices

| Slice | Status | Notes |
| --- | --- | --- |
| Clean-clone config and CI gate | done | PXE-0001, PXE-0003, PXE-0004, phase0-check. |
| API modernization blueprint and route inventory | done foundation | Blueprint and frozen inventory done; actual `/api/v1` migration open. |
| Offboard commander skeleton | done foundation | OffboardCommander, CommandIntent, failure policy, docs/tests done. Full FlightControlService/state-machine still partial. |
| Dashboard API client normalization | open | Dashboard warnings/deps improved, but one typed API client and CRA replacement remain open. |
| MavlinkAnywhere docs update | done foundation | Current ports/docs corrected; PXE-0022 remains for newer companion API/MCP standards. |

## Phase-by-Phase Status

| Original Phase | Status | Current Mapping |
| --- | --- | --- |
| Phase 0: baseline, governance, no-regression gates | done | PXE-0001 through PXE-0006, PXE-0011, PXE-0012, PXE-0015, PXE-0017, PXE-0009/0010. |
| Phase 1: runtime spine and ownership boundaries | partial | Gimbal provider boundary done. Command/Offboard boundaries done inside current structure. Full package/runtime/event/state split remains future cleanup. |
| Phase 2: flight safety and dedicated Offboard commander | mostly done at mock/unit level | PXE-0007, PXE-0013, PXE-0025 through PXE-0035 done. PX4-in-loop proof remains PXE-0037. |
| Phase 3: telemetry and target-loss pipeline | mostly done with API debt | Target loss, command freshness, MAVLink request freshness done. Typed telemetry health semantics remain PXE-0036. |
| Phase 4: API v1, command jobs, MCP | open | PXE-0008 and PXE-0022. |
| Phase 5: config/schema single source | partial | Schema drift and clean clone done; config resource/action API, dashboard parity, generated-schema enforcement still partial. |
| Phase 6: computer vision/tracking/model management | partial | Tracker contracts and L3 deterministic fixtures done; production tracker trace artifact and model-management hardening remain. |
| Phase 7: streaming and dashboard operator experience | open/partial | Existing dashboard CI and cleanup done; typed client, supported toolchain, stream capability negotiation, stale state UX remain. |
| Phase 8: MavlinkAnywhere/bootstrap/services/docs | partial | Linux/current docs corrected and companion refs tracked. Windows/X-Plane and latest sidecar standards remain. |
| Phase 9: tests/CI/SITL/HIL/evidence | partial | Unit/mock/full backend gates strong; SITL plan/action/evidence contracts exist; real fault injection and accepted runtime evidence remain. |
| Phase 10: legacy removal/repo hygiene | partial | Placeholder tests and stale gimbal docs removed. Broad legacy API/routes/docs/config cleanup remains. |
| Phase 11: release and field validation | open | No HIL/field/release evidence yet. |

## Open And In-Progress Issues

- PXE-0037 in progress: replace `manual_fault` placeholders with owned
  automated SITL injectors, automate PX4 params/ULog/tlog collection where
  supported, and improve operator-managed stack metadata capture.
- PXE-0038 open: production tracker or SmartTracker-backed deterministic smoke
  plus normalized trace artifact export.
- PXE-0020 open: decide X-Plane/Windows SITL future and align Windows
  MAVLink2REST defaults.
- PXE-0008 open: typed `/api/v1` routers, Pydantic models, structured errors,
  operation IDs, route migration tests.
- PXE-0022 open: re-review current companion standards before API/MCP/devops.
  Latest checked on 2026-06-02: MDS `v5.5.40-simurgh-git-status-summary` at
  `28bac599`, MavlinkAnywhere `v3.0.14` at `7643d4d`, Smart Wi-Fi Manager
  `v2.1.14` at `a5414fc`.
- PXE-0036 open: typed telemetry-health semantics under `/api/v1`.
- PXE-0024 open: dashboard must distinguish `has_output`, active tracking,
  stale/degraded data, and `usable_for_following`.
- PXE-0021 open: migrate dashboard from Create React App/react-scripts.
- PXE-0023 open: implement selected MAVLink Gimbal v2 or vendor gimbal
  providers behind `GimbalInputProvider`.

## Recommended Next Slices

1. Finish PXE-0037 runtime validation automation:
   add owned fault injectors for target loss, video stall, MAVSDK disconnect,
   MAVLink2REST timeout, and commander publish failure; keep control actions
   operator-gated.
2. Add PXE-0038 production tracker trace smoke:
   run a real tracker or SmartTracker-backed deterministic path through
   AppController/Follower/CommandIntent and export normalized trace artifacts.
3. Resolve PXE-0020:
   either rewrite X-Plane/Windows SITL as maintained artifacted evidence flow
   or move it to historical docs.
4. Start Phase 4 API/MCP:
   refresh MDS `v5.5.40` standards, define PixEagle structured error envelope,
   create first typed `/api/v1/system`, `/runtime`, `/tracking`, `/following`,
   `/telemetry-health`, and route migration tests.
5. Dashboard modernization:
   typed API client/status store first, stale tracker state UX next, then
   Vite/Vitest migration.
6. Gimbal provider expansion:
   choose hardware/protocol target before implementing MAVLink Gimbal v2 or a
   vendor provider.
7. Final cleanup phase:
   remove or deprecate legacy aliases, stale docs, duplicate configs, and
   unused scripts only after replacement tests and docs prove parity.

## Current Claim Boundary

No PX4 runtime SITL, HIL, real-aircraft, deployment, service installation, or
field validation was run for this reconciliation. Existing completed work is
supported by unit/mock/full-backend/docs/schema checks recorded in checkpoints,
not by real flight evidence.
