# Docs Infrastructure Staleness Inventory

Date: 2026-04-30  
Phase: 0  
Slice: 2

## Scope

This audit reconciled PixEagle's active infrastructure and configuration docs
against:

- the approved PixEagle modernization plan
- the current local `mavlink-anywhere` repository
- the current local `mavsdk_drone_show` API/MCP standards
- expert subagent reviews for docs, DevOps/bootstrap, and companion-project
  alignment

## Source-Of-Truth Updates Completed

The following source-of-truth docs were rewritten or corrected in this slice:

- `docs/drone-interface/04-infrastructure/mavlink-anywhere.md`
- `docs/drone-interface/04-infrastructure/mavlink-router.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/drone-interface/04-infrastructure/README.md`
- `docs/drone-interface/05-configuration/px4-config.md`
- `docs/drone-interface/05-configuration/mavlink-config.md`
- `docs/drone-interface/03-protocols/mavlink2rest-api.md`
- `README.md`
- `docs/INSTALLATION.md`
- `docs/README.md`

Those docs now teach:

- MavlinkAnywhere is the router installer/configurator, not MAVLink2REST.
- Current local endpoints are MAVSDK `127.0.0.1:14540`,
  MAVLink2REST input `127.0.0.1:14569`, local MAVLink
  `127.0.0.1:12550`, QGC `gcs_listen` on `14550/udp`, TCP server `5760`,
  and MavlinkAnywhere dashboard `127.0.0.1:9070`.
- MAVLink2REST HTTP binds to `127.0.0.1:8088` by default and uses
  `/v1/mavlink/...` paths.
- PixEagle's current app defaults are dashboard `3040`, backend `5077`,
  optional legacy telemetry WebSocket `5551`, and local MAVLink/MAVLink2REST
  endpoints.
- Clean clones can run from `configs/config_default.yaml`; `configs/config.yaml`
  is a local override, not a required checked-in file.
- `bash scripts/run.sh --no-dashboard` is the dashboard skip flag; `-d` is
  development mode.

## Guardrails Added

- `tests/test_docs_infrastructure_consistency.py` prevents the critical
  source-of-truth docs from reintroducing stale `14541`/`14551` style router
  snippets, stale `python main.py` entrypoints, stale lowercase config keys, and
  the old "MAVLink2REST is mavlink-anywhere" claim.
- CI now runs that docs guard with the Phase 0 guardrail tests.
- CI and `make phase0-check` now run shell syntax checks for scripts.

## Follow-Up Completed In Slice 3

Phase 0 Slice 3 closed the stale secondary-doc set that this inventory assigned
to PXE-0012. The following docs were reconciled with current
MavlinkAnywhere/config/API conventions:

- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/drone-interface/04-infrastructure/hardware-connection.md`
- `docs/drone-interface/04-infrastructure/companion-computer.md`
- `docs/drone-interface/06-development/adding-control-types.md`
- `docs/drone-interface/06-development/custom-telemetry.md`
- `docs/drone-interface/06-development/testing-without-drone.md`
- `docs/drone-interface/07-troubleshooting/connection-issues.md`
- `docs/drone-interface/07-troubleshooting/telemetry-gaps.md`
- `docs/drone-interface/07-troubleshooting/offboard-mode.md`
- `docs/drone-interface/05-configuration/safety-integration.md`

The docs consistency guard now covers those secondary pages. Manual stale
pattern scans only find explicit legacy notes in `port-configuration.md` and
`px4-config.md`.

## Stale Docs Originally Assigned To Follow-Up

At the end of Slice 2, the following docs still contained stale examples and
were assigned to the dedicated documentation cleanup slice:

- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/drone-interface/04-infrastructure/hardware-connection.md`
- `docs/drone-interface/04-infrastructure/companion-computer.md`
- `docs/drone-interface/06-development/custom-telemetry.md`
- `docs/drone-interface/06-development/testing-without-drone.md`
- `docs/drone-interface/07-troubleshooting/connection-issues.md`
- `docs/drone-interface/07-troubleshooting/telemetry-gaps.md`
- `docs/drone-interface/07-troubleshooting/offboard-mode.md`

Common patterns at assignment time:

- old `14541` MAVSDK and `14551` MAVLink2REST input examples
- old `/mavlink/...` paths instead of `/v1/mavlink/...`
- old `localhost:8000` backend examples instead of current `5077`
- direct `python main.py` entrypoints instead of `make run`,
  `bash scripts/run.sh`, or service-managed startup
- lowercase `px4.connection_string` and `mavlink2rest.base_url` snippets instead
  of current schema-backed `PX4.*` and `MAVLink.*` keys

Tracked as PXE-0012, closed in Slice 3.

## Related Runtime/Docs Risks

- Offboard docs still need a dedicated pass to avoid claiming an independent
  heartbeat before the Phase 2 flight-control service exists.
- Safety docs still need a code-and-doc pass around exact circuit-breaker
  semantics and fail-closed behavior.

Tracked as PXE-0013 and PXE-0007.
