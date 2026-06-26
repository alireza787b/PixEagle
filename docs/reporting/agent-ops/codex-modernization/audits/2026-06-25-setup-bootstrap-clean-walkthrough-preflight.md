# 2026-06-25 Setup And Bootstrap Clean-Walkthrough Preflight

## Scope

Read-only reviewer preflight for PXE-0068 and PXE-0074. No install, service,
deployment, PX4/SITL/HIL, field, or real-aircraft action was performed.

## Findings To Track Before Release/Handoff

1. macOS is advertised in some public installation paths, but `scripts/init.sh`
   is Debian/apt-oriented. Before macOS can be advertised as a beginner path,
   either add a maintained macOS bootstrap path or document macOS as unsupported
   by `scripts/init.sh`. First cleanup pass: Linux-only guided install wording
   and explicit macOS `install.sh` fail-fast behavior.

2. `scripts/init.sh` creates `venv`, while the Makefile defaults to
   `.venv/bin/python` before falling back to system `python3`. Clean-checkout
   setup-profile and validation commands must use the environment created by
   bootstrap or create the same environment name consistently. First cleanup
   pass: Makefile falls back to `venv/bin/python` before system `python3`.

3. Linux prerequisites in README and installation docs omit `make`, but the
   next documented command is `make init`. Minimal Ubuntu or Raspberry Pi
   images can fail before PixEagle setup starts. First cleanup pass: README,
   installation docs, and `scripts/init.sh` include `make`.

4. The manual dashboard `.env` step copies `dashboard/env_default.yaml` directly
   to `dashboard/.env`, while init converts that YAML-like template to dotenv
   syntax. Manual docs should use the same conversion path or provide a real
   dotenv template. First cleanup pass: installation docs use an explicit
   YAML-to-dotenv conversion snippet.

5. Manual Python setup still suggests installing the full `requirements.txt`,
   including AI-heavy packages. The clean walkthrough should preserve the
   safer core/AI split used by `scripts/init.sh`. First cleanup pass:
   installation docs use the same core-first filter and point AI setup to the
   deterministic scripts.

6. `scripts/init.sh` can print "Setup Complete" even when dashboard dependency
   setup or binary downloads were skipped or failed. The release walkthrough
   needs explicit artifact checks and summary language that distinguishes
   ready, degraded, skipped, and manual-follow-up states.

7. `scripts/run.sh` can terminate any process on configured ports before
   startup and uses `nc` for readiness checks, but netcat is not installed by
   the documented prerequisites. The run path should avoid killing unrelated
   processes by default and document/install readiness dependencies. First
   cleanup pass: `scripts/run.sh` terminates only PixEagle-owned listener PIDs,
   blocks on foreign port occupants, and falls back to Python socket readiness
   when `nc` is absent.

8. Installation verification currently leans on `python src/test_Ver.py`, which
   only proves OpenCV import/build information. The handoff walkthrough should
   include schema, route inventory, setup-profile dry-run, binary dry-run or
   provenance checks, dashboard test/build, and local-only network-posture
   evidence.

## Clean-Walkthrough Commands To Prove Later

```bash
tmp="$(mktemp -d)"
git clone --depth 1 https://github.com/alireza787b/PixEagle.git "$tmp/PixEagle"
cd "$tmp/PixEagle"
PIXEAGLE_INSTALL_PROFILE=core PIXEAGLE_NONINTERACTIVE=1 bash scripts/init.sh
make setup-profile PROFILE=local_dev SETUP_PROFILE_ARGS=--dry-run
PYTHON="$PWD/venv/bin/python" make setup-profile PROFILE=local_dev SETUP_PROFILE_ARGS=--dry-run
bash scripts/setup/download-binaries.sh --all --dry-run
PYTHON="$PWD/venv/bin/python" bash scripts/check_schema.sh
PYTHONPATH=src "$PWD/venv/bin/python" -m pytest \
  tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py \
  -ra --tb=short
(cd dashboard && npm test -- --watchAll=false && npm run build)
```

Additional isolated checks should cover minimal Ubuntu/Raspberry Pi packages,
manual dashboard dotenv generation, missing `nc`, and port-conflict behavior
without terminating unrelated user processes.

## Evidence Required To Close

- OS image/version, architecture, git commit, and exact command transcript.
- Exit code and generated files for beginner demo and senior-dev override paths.
- Binary provenance or explicit skipped/manual-follow-up status.
- Dashboard dependency, test, and build output.
- Schema and route-inventory output.
- Ports and bind addresses after profile application.
- Credential handoff behavior for browser/session or QGC media profiles.
- List of docs/scripts changed to remove stale or confusing instructions.
