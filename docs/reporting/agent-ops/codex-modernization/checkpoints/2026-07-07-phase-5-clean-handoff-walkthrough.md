# Phase 5 Checkpoint: Clean Setup/Update Handoff Walkthrough

Date: 2026-07-07
Slice: PXE-0074 partial
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

This slice adds a repeatable clean-checkout setup/update handoff harness and
captures the first current-branch evidence pass for the beginner and senior-dev
documentation paths.

The checkpoint proves only dry-run/check-only setup and update behavior from a
temporary clean checkout. It does not claim service installation, live firewall
changes, MAVSDK/MAVLink2REST binary download success, QGC playback, dashboard
clean-clone npm install/build in the default lane, PX4/SITL/HIL, field
behavior, tracker/follower response, or real aircraft readiness.

## Files Changed

- `README.md`
- `docs/INSTALLATION.md`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-07-pxe0074-clean-handoff-walkthrough/`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-07-07-phase-5-clean-handoff-walkthrough.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `tests/test_setup_handoff_walkthrough.py`
- `tools/run_setup_handoff_walkthrough.py`

## Behavior

`tools/run_setup_handoff_walkthrough.py` now:

- refuses to collect handoff evidence from a dirty source worktree by default;
- clones the selected branch into a temporary checkout;
- verifies required public setup/docs/config files exist;
- runs shell syntax checks for setup, launch, demo, cleanup, and sync scripts;
- runs `make help`;
- previews pinned MAVSDK/MAVLink2REST binary downloads with `--dry-run`;
- runs `local_dev`, `field_qgc_video`, `demo_lan_browser`,
  `qgc_direct_media`, and `production_remote` setup-profile dry-runs;
- runs `make quick-browser-demo` and `make quick-browser-demo-cleanup` in
  no-touch dry-run mode with no service start and no firewall changes;
- runs the clean-worktree fast-forward update check with `scripts/lib/sync.sh`;
- runs schema and minimum backend/API Phase 0 checks;
- records each command's stdout/stderr logs, hashes, return code, and duration
  in an evidence manifest;
- optionally supports a heavier `--include-dashboard` clean-clone npm
  install/test/build lane for final release candidates. That optional lane may
  fetch npm package artifacts from the configured npm registry.

The public docs now point maintainers to this walkthrough and state its
non-claims.

## Evidence

Manifest:

```text
docs/reporting/agent-ops/codex-modernization/evidence/2026-07-07-pxe0074-clean-handoff-walkthrough/manifest.json
```

Source commit under test:

```text
a703260a9d256f171478df7d98fbba4bdd6ced01
```

The manifest reports:

- source worktree clean at start: `true`;
- temporary checkout preserved: `false`;
- required files: pass;
- command count: 22;
- passed commands: 22;
- failed commands: none;
- final checkout status: clean.

Commands proven by the manifest include:

- `make help`;
- shell syntax checks for setup/launch/demo/sync scripts;
- `bash scripts/setup/download-binaries.sh --all --dry-run`;
- profile dry-runs for local, QGC field video, browser demo, QGC direct media,
  and production remote;
- quick browser demo dry-run and cleanup dry-run;
- clean-worktree fast-forward sync check;
- `bash scripts/check_schema.sh`;
- `PYTHONPATH=src python -m pytest tests/test_api_route_inventory.py
  tests/unit/core_app/test_parameters_reload.py -q`.

## Validation

Passed before committing the harness:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_setup_handoff_walkthrough.py tests/test_docs_infrastructure_consistency.py -q
# 25 passed
```

```bash
.venv/bin/python -m py_compile tools/run_setup_handoff_walkthrough.py tests/test_setup_handoff_walkthrough.py
```

```bash
bash scripts/check_schema.sh
# Schema is up-to-date.
```

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py -q
# 54 passed
```

Clean-checkout evidence run:

```bash
.venv/bin/python tools/run_setup_handoff_walkthrough.py --run-id 2026-07-07-pxe0074-clean-handoff-walkthrough --python /home/alireza/PixEagle/.venv/bin/python
# PASS, 22/22 commands
```

Final validation for this checkpoint is recorded in the final slice report and
commit message.

## Review

Independent read-only reviewers found and the slice fixed:

- final checkout cleanliness was overclaimed because `git status` exits `0`
  even when the checkout is dirty. The harness now parses
  `git status --short --branch` output and fails `git_status_initial` or
  `git_status_final` when any non-branch status line appears;
- source worktree cleanliness metadata was confusing because later manifest
  capture saw the generated evidence directory. The harness now records
  `source_git_status_at_start` before creating evidence artifacts and separates
  it from temporary checkout status;
- `--include-dashboard` could run `npm ci`, so docs now state that optional
  dashboard evidence may fetch npm package artifacts while the default lane does
  not install npm packages or download MAVSDK/MAVLink2REST binaries;
- installation docs now scope the QGC `14550/udp` firewall example to a trusted
  GCS IP/CIDR;
- README now puts the service-install warning before any sudo service commands;
- `python src/test_Ver.py` is now labeled as an OpenCV diagnostic, not release
  verification;
- stale phase-map wording around PXE-0079 was removed.

## Residual Risk

- The default evidence pass did not run `--include-dashboard`; prior dashboard
  gates exist, and the harness can run the heavier clean-clone dashboard lane
  before a final release candidate or after frontend changes. That optional
  lane may fetch npm package artifacts.
- No live service install, live firewall mutation, MAVSDK/MAVLink2REST binary
  download, QGC playback, PX4/SITL/HIL, field test, or real-aircraft behavior
  was performed.
- The evidence commit predates this checkpoint/report commit. Re-run the
  harness on the final release branch before tagging if exact report-commit
  evidence is required.
- Production remote target evidence still requires selected host/proxy/TLS,
  firewall, service-account, credential handoff, adversarial browser/media
  tests, and operator acceptance.
- The active public HTTP demo credential was intentionally not rotated in this
  slice; cleanup/rotation remains tied to the current tester session.

## Next Slice

Continue the planned modernization queue. Recommended next gates:

1. Finish PXE-0074 release-candidate evidence later with
   `--include-dashboard`, tag dry run, and final clean branch proof.
2. Continue PXE-0064/PXE-0068 production target evidence when a target
   TLS/proxy/firewall/service setup is selected.
3. Keep QGC PR #13594 draft until authenticated generic/PixEagle media is
   tested end to end.
