# Phase 4 Binary Download Provenance

Date: 2026-06-17  
Slice: PXE-0068 binary download provenance  
Status: completed; PXE-0068 remains in progress for remote-profile automation
and media/service follow-ups  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

This slice closed the PXE-0068 gate for MAVSDK Server and MAVLink2REST binary
download pins, overrides, checksum verification, provenance, and Linux/Windows
parity.

It did not download or install binaries during validation. The only exercised
runtime path was dry-run planning.

## Decisions

- `scripts/setup/binary-manifest.env` is the setup-time source of truth for
  external helper binaries.
- Default download paths use exact release tags, exact asset names, and
  SHA-256 digests. They do not use `latest` URLs or fallback tag probing.
- MAVSDK Server is pinned to upstream `mavlink/MAVSDK` release `v3.12.0`.
- MAVLink2REST is pinned to upstream `mavlink/mavlink2rest` release `1.0.0`.
- Linux/macOS and Windows downloaders consume the same manifest.
- `--dry-run` / `--print-plan` prints platform, version, release URL, asset,
  download URL, expected SHA-256, destination, and provenance path without
  writing files.
- Verified installs and accepted existing binaries append JSONL evidence to
  `bin/binary-provenance.jsonl`.
- Existing `bin/` binaries are not silently accepted by init; init now routes
  them through downloader verification so provenance can be written.
- Root-level legacy binaries no longer count as installed during init
  summaries. The Linux downloader can still migrate a verified root-level
  legacy binary into `bin/`; unverified root-level binaries do not satisfy setup.
- Unverified custom URLs/assets are rejected by default. Lab-only unverified
  overrides require `PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1` and record
  `verification_mode=unverified_override`; that mode is not valid evidence for
  production, SITL success claims, HIL, field testing, or tester handoff.

## Files Changed

- `scripts/setup/binary-manifest.env`
- `scripts/setup/download-binaries.sh`
- `scripts/setup/download-binaries.bat`
- `scripts/init.sh`
- `scripts/init.bat`
- `Makefile`
- `.github/workflows/tests.yml`
- `README.md`
- `docs/README.md`
- `docs/INSTALLATION.md`
- `docs/WINDOWS_SETUP.md`
- `docs/setup/setup-profiles.md`
- `docs/setup/binary-download-policy.md`
- `tests/test_binary_download_policy.py`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`

## Review

Two read-only reviewers independently inspected the slice.

Reviewer findings that were fixed:

- Linux downloader could fall through to success after failed component
  downloads.
- Checksum helpers and dry-run/provenance behavior were partially advertised but
  not fully wired.
- Windows used fallback release tag and asset probing, so the same beginner
  command could install different versions than Linux.
- Linux/macOS platform mapping had stale ARMv6 and macOS ARM64 behavior.
- Init scripts accepted existing or legacy binaries without manifest
  verification/provenance.
- Docs still normalized unverified/manual binary placement and did not explain
  dry-run, pins, checksums, or provenance.

Remaining reviewer notes recorded as future work:

- Production deployment evidence should include `bin/binary-provenance.jsonl`
  alongside SITL/HIL/field artifacts whenever local MAVSDK Server or
  MAVLink2REST binaries are involved.
- A later packaging slice can replace shell/batch duplication with a shared
  Python resolver if setup grows beyond simple manifest fields.

## External References Checked

- MAVSDK release `v3.12.0`:
  <https://github.com/mavlink/MAVSDK/releases/tag/v3.12.0>
- MAVLink2REST release `1.0.0`:
  <https://github.com/mavlink/mavlink2rest/releases/tag/1.0.0>
- GitHub release API metadata for those releases was used to capture upstream
  asset `digest` SHA-256 values for the checked-in manifest.

## Validation

Passed:

```bash
bash -n scripts/setup/download-binaries.sh scripts/init.sh install.sh
```

```bash
.venv/bin/python -m py_compile \
  tests/test_binary_download_policy.py \
  tests/test_setup_profiles.py \
  tests/test_docs_infrastructure_consistency.py
```

```bash
make binary-download-plan
```

Result: dry-run printed the pinned Linux x86_64 MAVSDK Server and MAVLink2REST
plan with expected SHA-256 values and no file writes.

```bash
.venv/bin/python -m pytest \
  tests/test_binary_download_policy.py \
  tests/test_setup_profiles.py \
  tests/test_docs_infrastructure_consistency.py \
  -ra --tb=short --strict-config
```

Result: 37 passed.

```bash
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current, API tool candidate inventory current, 217 passed with
the existing Starlette/httpx `TestClient` deprecation warning.

```bash
git diff --check
```

Result: exit code 0 with the expected CRLF normalization warning for the edited
Windows batch file.

## Not Performed

- No binary download or install.
- No service install/start/enable.
- No sidecar mutation/update.
- No QGC branch mutation or build.
- No PX4/SITL/HIL/field run.
- No deployment.
- No runtime MCP endpoint or callable tool exposure.
- No real-aircraft control.

## Remaining PXE-0068 Work

- Decide whether to automate `demo_lan_browser` credential generation in a later
  slice; it must generate external hashed users, exact Host/CORS, warning
  banners, and evidence before it can write config.
- Keep `production_remote` deferred until TLS/operator hardening, credential
  rollout, adversarial auth/media tests, and evidence gates are ready.
- Add a dedicated backend media WebSocket health probe so service status can
  report telemetry socket health and media WebSocket health separately.
- Continue setup/update cleanup for any additional stale binary/service/download
  docs found during later slices.

## Next Planned Slice

Continue Phase 4 with API/MCP candidate disposition governance (PXE-0066) or
SITL sidecar evidence hardening (PXE-0065), unless the maintainer prioritizes
remote browser credential-generation automation under PXE-0068.
