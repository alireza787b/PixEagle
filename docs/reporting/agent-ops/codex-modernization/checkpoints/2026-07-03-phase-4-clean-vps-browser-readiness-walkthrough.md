# 2026-07-03 Phase 4 Clean VPS Browser Readiness Walkthrough

## Phase / Slice

- Phase 4 setup, bootstrap, and browser handoff readiness
- Issues: PXE-0068 partial; PXE-0074 in progress
- Scope: run a clean temporary checkout walkthrough on the VPS, verify the
  beginner/core setup path and controlled local browser smoke, and capture the
  blockers/fixes before any user handoff.

This checkpoint includes a browser/API smoke for local-only PixEagle services.
It does not claim MAVSDK Server, MAVLink2REST, MavlinkAnywhere routing, PX4,
SITL, HIL, QGroundControl playback, field behavior, or real-aircraft success.

## Repository Context

- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Clean-clone code commit used for the main walkthrough: `03927605`
  (`PXE-0074 restore shared shell helper`)
- Previous readiness estimate:
  `checkpoints/2026-07-03-phase-4-vps-browser-test-readiness-estimate.md`
- Host date: 2026-07-03 UTC

## What Was Proven

- A clean checkout of the current branch can initialize in Core profile without
  a local `configs/config.yaml`.
- The missing shared shell helper discovered during the first walkthrough
  attempt is fixed by checked-in `scripts/lib/common.sh`, and `.gitignore` no
  longer hides `scripts/lib/`.
- Core init creates/reuses the Python venv, installs core Python packages,
  installs dashboard dependencies, creates `dashboard/.env`, keeps runtime
  config on checked-in defaults, and downloads/verifies manifest-pinned MAVSDK
  Server and MAVLink2REST binaries.
- Setup-profile dry-run, schema check, minimum backend/API gates, dashboard
  tests, and dashboard production build passed from the clean checkout.
- A controlled local-only smoke with MAVSDK Server and MAVLink2REST explicitly
  skipped served:
  - backend on `127.0.0.1:5077`;
  - dashboard on `127.0.0.1:3040`;
  - typed reads for `/api/v1/runtime/status`,
    `/api/v1/tracking/catalog`, and `/api/v1/streams/media-health`.
- Services were stopped after the smoke and no PixEagle listener remained on
  ports `3040`, `5077`, or `5551`.

## Commands And Results

The first clean clone attempt failed because the VPS root filesystem was nearly
full:

```bash
git clone --branch codex/modernization-pxe0040-runtime-20260604 --single-branch https://github.com/alireza787b/PixEagle.git /tmp/pixeagle-pxe0074-clean-zmxV5n/PixEagle
```

Result: failed with `No space left on device`.

Disk/cache cleanup performed before retry:

```bash
npm cache clean --force
pip cache purge
rm -rf /home/alireza/.npm/_npx /tmp/pixeagle-pxe0074-clean-zmxV5n
```

No Docker prune was performed in this slice.

Clean clone after cleanup:

```bash
git clone --branch codex/modernization-pxe0040-runtime-20260604 --single-branch https://github.com/alireza787b/PixEagle.git /tmp/pixeagle-pxe0074-clean-yC8agu/PixEagle
git rev-parse --short HEAD
```

Result: `03927605`.

Core init:

```bash
PIXEAGLE_INSTALL_PROFILE=core PIXEAGLE_NONINTERACTIVE=1 bash scripts/init.sh
```

Result: passed. The earlier `common.sh` warning did not recur after commit
`03927605`.

Setup/profile and backend gates:

```bash
make setup-profile PROFILE=local_dev SETUP_PROFILE_ARGS=--dry-run
PYTHON="$PWD/venv/bin/python" make setup-profile PROFILE=local_dev SETUP_PROFILE_ARGS=--dry-run
bash scripts/setup/download-binaries.sh --all --dry-run
PYTHON="$PWD/venv/bin/python" bash scripts/check_schema.sh
PYTHONPATH=src "$PWD/venv/bin/python" -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -ra --tb=short
```

Results:

- setup-profile dry-runs passed;
- binary download dry-run passed;
- schema check passed with 41 sections, 549 parameters, and 9 categories;
- minimum backend/API gate passed: 50 tests.

Dashboard gates from the clean checkout:

```bash
npm test -- --watchAll=false
npm run build
```

Results:

- dashboard tests passed: 20 suites, 120 tests;
- dashboard production build passed;
- build still emits the known CRA/Node deprecation warning tracked under
  PXE-0021.

Controlled local-only smoke:

```bash
bash scripts/run.sh --no-attach -m -k
```

The `-m` and `-k` flags intentionally skipped MAVLink2REST and MAVSDK Server.
This smoke verifies dashboard/backend startup only.

Probes:

```bash
curl -fsS -m 5 http://127.0.0.1:5077/api/v1/runtime/status
curl -fsSI -m 5 http://127.0.0.1:3040/
curl -fsS -m 5 http://127.0.0.1:5077/api/v1/tracking/catalog
curl -fsS -m 5 http://127.0.0.1:5077/api/v1/streams/media-health
lsof -nP -iTCP:3040 -sTCP:LISTEN
bash scripts/stop.sh
lsof -nP -iTCP:3040 -sTCP:LISTEN
lsof -nP -iTCP:5077 -sTCP:LISTEN
lsof -nP -iTCP:5551 -sTCP:LISTEN
```

Results:

- runtime status returned process-local state with PX4 disconnected and
  MAVLink telemetry unavailable because MAVLink2REST was intentionally skipped;
- dashboard eventually returned `HTTP/1.1 200 OK` and served the PixEagle
  Dashboard `index.html`;
- tracker catalog returned typed catalog data; `SmartTracker` remained
  unavailable in Core profile because AI packages were intentionally skipped;
- media health returned `status: idle`, `exposure_mode: local_only`,
  `bind_host: 127.0.0.1`, and `auth_mode: local_compat`;
- dashboard listener was bound to `127.0.0.1:3040`;
- stop script terminated the PixEagle tmux session and no PixEagle listeners
  remained on the checked ports.

## Fixes Landed From This Walkthrough

- Added `scripts/lib/common.sh`, the shared shell helper expected by bootstrap
  and runtime scripts.
- Changed `.gitignore` from broad `lib/`/`lib64/` ignores to root-scoped
  `/lib/` and `/lib64/` so `scripts/lib/` remains tracked.
- Hardened `scripts/components/dashboard.sh` so direct component startup no
  longer kills whatever process happens to own the dashboard port. It now
  reports the listener and exits.
- Suppressed npm audit/fund noise in setup/runtime dependency installation
  paths; audit/toolchain debt remains tracked separately as PXE-0021.
- Changed `scripts/init.sh` to prefer `npm ci` when a lockfile exists and to
  prime the dashboard launcher's dependency hash after successful dependency
  setup.
- Added service-specific readiness waits in `scripts/run.sh`: dashboard first
  run now gets a longer default wait because production build time is naturally
  longer than backend port startup. Overrides are available through
  `PIXEAGLE_DASHBOARD_READY_RETRIES`,
  `PIXEAGLE_BACKEND_READY_RETRIES`, and
  `PIXEAGLE_MAVLINK2REST_READY_RETRIES`; invalid override values fall back to
  safe positive defaults.

## Validation On Main Working Tree

Run after the startup fixes:

```bash
bash -n scripts/lib/common.sh scripts/components/dashboard.sh scripts/init.sh scripts/run.sh scripts/stop.sh scripts/setup/download-binaries.sh scripts/setup/install-ai-deps.sh scripts/setup/setup-pytorch.sh scripts/setup/check-ai-runtime.sh scripts/setup/install-dlib.sh scripts/setup/build-opencv.sh
NO_COLOR=1 bash scripts/components/dashboard.sh --help
NO_COLOR=1 bash scripts/run.sh --help
bash -c 'set -euo pipefail; source <(sed -n "/^positive_integer_or_default()/,/^wait_for_services()/p" scripts/run.sh | sed "\$d"); test "$(PIXEAGLE_DASHBOARD_READY_RETRIES=abc service_ready_retries Dashboard)" = "120"; test "$(PIXEAGLE_BACKEND_READY_RETRIES=7 service_ready_retries Backend)" = "7"; test "$(PIXEAGLE_SERVICE_READY_RETRIES=0 service_ready_retries Other)" = "15"'
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_setup_profiles.py::test_init_summary_tracks_dashboard_and_binary_followup_states tests/test_setup_profiles.py::test_run_script_blocks_foreign_port_owners_and_has_no_netcat_dependency tests/test_setup_profiles.py::test_run_script_normalizes_service_ready_retry_overrides -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist -q
PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -ra --tb=short
bash scripts/check_schema.sh
npm test -- --watchAll=false
npm run build
git diff --check
```

Results:

- shell syntax/help checks passed;
- retry override normalization probe passed;
- focused setup-profile regression checks passed: 3 tests;
- docs local-link gate passed: 1 test;
- minimum backend/API gate passed: 50 tests;
- schema check passed and schema is current;
- dashboard tests passed: 20 suites, 120 tests;
- dashboard production build passed with the known CRA/Node
  `[DEP0176] fs.F_OK` deprecation warning tracked under PXE-0021;
- whitespace diff check passed.

## VPS Host Risk

The VPS root filesystem remains tight. Before cleanup, the corrected temporary
checkout used about 2.3 GB and `/` showed about 1.6 GB free. The temp checkout
should be removed after this report is finalized, and future Docker/Gazebo/QGC
work should use a larger workspace or planned cleanup window.

## Claim Boundary

This checkpoint proves clean setup and local-only dashboard/backend smoke on
this VPS for the exact commands above.

It does not prove:

- public browser access;
- SSH tunnel or private-overlay user browser access;
- `demo_lan_browser` or `production_remote` credential handoff on this host;
- target TLS/reverse-proxy/firewall readiness;
- MAVSDK Server runtime behavior;
- MAVLink2REST runtime behavior;
- MavlinkAnywhere routing;
- tracker/follower closed-loop behavior;
- PX4/SITL/HIL/field behavior;
- QGroundControl media playback;
- any real-aircraft behavior.

## Estimate Update Before First User Browser Test

The previous estimate said the first controlled browser review needed 2 focused
slices, or 3 if host/package/port blockers appeared. One of those slices is now
complete.

Remaining before the first user-visible VPS/browser test:

1. Choose the handoff lane:
   - default recommendation: SSH tunnel or private overlay/local-only browser
     review;
   - alternative: `demo_lan_browser` for isolated LAN/private-overlay HTTP with
     generated browser-session credentials;
   - production public HTTPS/WSS remains a separate evidence-backed path.
2. Start services from the reviewed branch with the chosen posture.
3. Verify bind addresses and typed API reads again after profile selection.
4. Hand off the browser URL and any credentials outside the repository.
5. Capture a short checkpoint with sanitized logs and explicit claim boundary.

If SSH/local-only or private overlay is acceptable, the first controlled
browser test is now about one focused handoff slice away, assuming the VPS disk
space is cleaned before startup. Public production HTTPS/WSS still needs the
previously estimated 2 to 5 additional evidence slices depending on TLS,
reverse proxy, firewall, service ownership, credential handoff, and adversarial
auth/media test readiness.

## Remaining Slices After This Checkpoint

- Controlled user browser handoff on VPS: one focused slice for SSH/local-only
  or private-overlay/lab profile access.
- Production remote evidence: target TLS/proxy/firewall/service-account,
  credential handoff, target-host adversarial checks, and operator acceptance.
- QGC PR #13594 receiver evidence: keep the PR draft until target playback and
  authenticated PixEagle media evidence are accepted.
- PXE-0021 dashboard toolchain modernization: migrate away from CRA/react-
  scripts and remove dev-toolchain audit/deprecation debt.
- PXE-0008 remaining API work: broader typed tracker configuration mutation
  and other future route-boundary debt discovered by static guards.
- PX4/SITL/Gazebo/X-Plane validation ladder: separate evidence slices before
  any flight-adjacent handoff claim.

## Reviewer Result

Independent read-only checkpoint review found one blocker before commit: the
PXE-0074 reporting needed to be updated from estimate-only status to the actual
clean-walkthrough evidence. This checkpoint, the July journal, the phase map,
and the issue register were updated accordingly.

The reviewer also found one low-risk startup concern: invalid
`PIXEAGLE_*_READY_RETRIES` environment values could feed directly into Bash
arithmetic. That concern was fixed before commit by normalizing retry overrides
to positive integers with safe defaults and adding a setup-profile regression
guard.

No remaining startup-code blocker was reported. The reviewer agreed the claims
are safe when limited to clean clone/Core init, setup dry-runs, validation
gates, local-only backend/dashboard startup, and typed API responses, and
agreed the first controlled user browser test is now about one focused handoff
slice away for SSH/local-only or private-overlay access.
