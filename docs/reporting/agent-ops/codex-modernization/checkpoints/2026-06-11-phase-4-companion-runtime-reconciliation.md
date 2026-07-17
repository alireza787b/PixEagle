# Phase 4 Companion Runtime Reconciliation Checkpoint

Date: 2026-06-11
Slice: PXE-0022
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: reconcile PixEagle API/MCP/runtime policy and active operator guidance
with current MDS, MavlinkAnywhere, and Smart Wi-Fi Manager contracts.

## Outcome

PXE-0022 is complete as a companion-contract and documentation-reconciliation
slice.

PixEagle now has one canonical companion-runtime contract covering:

- ownership boundaries between PixEagle, MavlinkAnywhere, MAVLink2REST,
  optional Smart Wi-Fi Manager, and external orchestration;
- local-first management exposure;
- remote browser Basic Auth plus CSRF and machine bearer-token requirements;
- process-local dry-run plans, explicit confirmed apply, policy-mode meanings,
  and Smart Wi-Fi service-mode separation;
- secret handling, exact per-deployment version/evidence pins, and reviewed
  capability references;
- read-only health versus prepared-routing evidence;
- prohibition of agent-specific bypass access to non-PixEagle
  drone/PX4/MAVSDK/MAVLink2REST/sidecar surfaces;
- candidate review disposition without mandatory MCP promotion;
- explicit deferral of callable MCP, web search, assistant streaming UX,
  drone-log tools, and action-enabled agents.

Active routing, SITL, API, architecture, installation, troubleshooting, port,
configuration, Windows/X-Plane disposition, and agent-context docs now align
with this contract. Active docs no longer teach unqualified PixEagle
LAN/firewall exposure, remote unauthenticated configuration as acceptable,
stale Windows/X-Plane execution, or pulling MavlinkAnywhere `main` as a
deployment update. Initial MavlinkAnywhere root installation now follows an
explicit validated revision checkout.

Independent review exposed two broader runtime gaps, now tracked rather than
hidden:

- PXE-0064: production PixEagle API authentication/exposure boundary;
- PXE-0065: SITL sidecar version/compatibility/preparation classification and
  evidence secret scanning.
- PXE-0066: explicit approved/blocked/deferred candidate-disposition
  governance without runtime promotion.

No sidecar mutation, service installation/update/restart, routing change,
PX4/SITL/HIL/field operation, or real-aircraft control was performed or
claimed.

## Exact References

| Repository | Reviewed revision |
| --- | --- |
| PixEagle before slice | `eafbc63cc6e2a43a96521a31d1c2a4e899648fbf` |
| MDS | `623bb3fa2cc7e8ab4fe6de032425c1aa17e05186`, `v5.5.71-simurgh-readonly-closure` |
| MavlinkAnywhere | `7643d4d9bc75a78fdc6b0f68358c466310ee2c4d`, `v3.0.14-2-g7643d4d` |
| Smart Wi-Fi Manager | `a5414fc7d7df1fde47db11aeed1681f5515ea350`, `v2.1.14-2-ga5414fc` |

All companion worktrees were clean and synchronized with `origin/main` after
`git fetch --prune --tags`.

## Read-Only Local Probe

Read-only loopback probes found:

- MavlinkAnywhere `GET /api/v1/status`: HTTP 200, installed version `v3.0.8`,
  zero endpoints;
- diagnostics: HTTP 200 with critical `config_parse_failed` because
  `/etc/mavlink-router/main.conf` is missing;
- endpoints/config: HTTP 500;
- profile summary: HTTP 404 because the installed dashboard predates that
  contract;
- health: HTTP 200;
- Smart Wi-Fi Manager `127.0.0.1:9080`: connection refused.

Conclusion: the local MavlinkAnywhere process is alive but old and unprepared.
It is not accepted routing evidence and does not demonstrate current upstream
contract drift.

## Files Changed

- `README.md`
- `docs/INSTALLATION.md`
- `docs/README.md`
- `docs/TROUBLESHOOTING.md`
- `docs/CONFIGURATION.md`
- `docs/WINDOWS_SITL_XPLANE.md`
- `docs/agent-context/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/architecture/companion-runtime-contract.md`
- `docs/architecture/pixeagle-modernization-blueprint.md`
- `docs/drone-interface/04-infrastructure/README.md`
- `docs/drone-interface/04-infrastructure/mavlink-anywhere.md`
- `docs/drone-interface/04-infrastructure/port-configuration.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-06-11-companion-runtime-reconciliation.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `tests/test_docs_infrastructure_consistency.py`

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py -q`:
  13 passed.
- `PYTHON=.venv/bin/python make phase0-check`:
  schema current, candidate inventory current, 60 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q`:
  34 passed.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`:
  schema current.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`:
  candidate inventory current.
- Active-doc stale/unsafe scan for unconditional `ufw allow 5077`, unqualified
  dashboard LAN wording, `MavlinkAnywhere | Current`, and active
  MavlinkAnywhere `git pull --ff-only`: no active matches.
- `git diff --check`: passed.

A bare `bash scripts/check_schema.sh` used system Python and failed because
system Python does not have `ruamel`; the repository venv command above passed.
No dependency change was required.

## Review

Initial API/MCP and security/devops reviewers found no reason to copy MDS or
sidecar implementations wholesale. Their actionable findings were incorporated:

- direct agent bypass paths to non-PixEagle drone/sidecar surfaces prohibited;
- review disposition separated from promotion;
- future result/event contracts required to be typed/versioned;
- process-local dry-run and acknowledgement semantics documented;
- Smart Wi-Fi service mode separated from profile reconciliation mode;
- update procedure pinned to a validated tag/commit;
- unsafe broad PixEagle firewall/LAN guidance removed;
- stale Windows/X-Plane steps replaced with an unmaintained-path disposition;
- runtime authentication and sidecar evidence gaps registered as PXE-0064 and
  PXE-0065.

Final finished-diff security/devops and API/MCP reviewers found no untracked
closure blocker after their findings were resolved or assigned:

- stale troubleshooting/configuration/Windows-X-Plane exposure guidance and
  unpinned initial MavlinkAnywhere install were corrected;
- the agent HTTP wording now permits the reviewed typed PixEagle API while
  prohibiting bypass/non-PixEagle surfaces;
- explicit candidate-disposition implementation is tracked as PXE-0066;
- MDS MCP wording now identifies the canonical environment default and allows
  reviewed specialized launch overrides.

## Risks And Open Work

- The current PixEagle backend remains broadly bound, wildcard-CORS, and
  unauthenticated; docs now warn operators, but PXE-0064 must implement the
  production boundary.
- The SITL harness still lacks installed sidecar version/capability acceptance,
  precise preparation-failure classification, and artifact secret scanning;
  PXE-0065 must implement these before accepted production-grade evidence.
- Candidate approved/blocked/deferred disposition is policy only until
  PXE-0066 implements generator/registry/policy coverage and tests.
- The local MavlinkAnywhere `v3.0.8` service remains unprepared. No mutation was
  authorized in this slice.
- Companion reviewed source revisions are capability references, not validated
  deployment pins.

## Next Slice

Prioritize PXE-0064 because unauthenticated remote control/API exposure is the
highest-severity newly confirmed gap. Then implement PXE-0066 candidate
dispositions and PXE-0065 sidecar evidence hardening before relying on runtime
agent governance or accepted companion-sidecar evidence. Continue PXE-0008
typed API/router extraction and PXE-0021 dashboard toolchain modernization
around those safety gates.
