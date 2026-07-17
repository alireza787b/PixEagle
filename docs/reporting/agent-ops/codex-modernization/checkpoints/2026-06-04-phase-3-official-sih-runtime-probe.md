# Phase 3 Checkpoint: Official SIH Runtime Probe

Date: 2026-06-04
Phase/slice: Phase 3, PXE-0039 runtime probe and PXE-0042 precursor
Status: incomplete runtime evidence; official SIH startup and artifact capture
proved, full PixEagle/PX4 interaction still not claimed
Claim boundary: guarded PX4 SIH container startup, metadata, params, ULog, and
stdout evidence only. This is not a PixEagle tracker/follower pass, Offboard
mode pass, Gazebo/visual SITL pass, HIL, field, deployment, service-install, or
real-aircraft validation.

## Summary

The active PX4 SIH profile still referenced `px4io/px4-sitl:v1.17.0`, which is
not a pullable Docker Hub tag. The active SIH plan, wrapper, workflow, helper
script, docs, and tests now use the pullable v1.17-family official image:

```text
px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01
px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865
```

The guarded `execute-px4` run started only a harness-owned PX4 SIH container
with `PX4_SIM_MODEL=sihsim_quadx`, verified the ownership labels and container
ID, collected image/container metadata, matched the expected repo digest,
copied PX4 params, and copied one ULog from the container.

The run correctly remained incomplete. PixEagle, MAVLink2REST, complete
MavlinkAnywhere route/profile evidence, scenario results, PixEagle backend log,
and PX4 tlog evidence were not present. The result is useful L2 infrastructure
evidence, not an accepted PixEagle/PX4 behavior pass.

This probe also exposed a harness quality issue: PX4's interactive shell emits
millions of `pxh>` redraws over carriage returns. The first SIH probe wrote a
159 MB `logs/px4_sitl.log` in about 20 seconds. The harness now captures PX4
stdout through a bounded scrubber that removes prompt redraw spam, caps managed
PX4 stdout at 4 MiB by default, flushes the file while the process runs, and
records capture metadata in the manifest. The final reviewed evidence run
reduced 162,054,071 raw stdout bytes to a readable 2,574 byte log while preserving PX4
startup, MAVLink, logger, arming-health, and shutdown lines.

## Files Changed

- `tools/sitl_plans/phase2_follower_validation.json`
  - Replaced the nonexistent SIH image tag with
    `px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01`.
  - Added required image/container metadata and expected repo digest.
- `scripts/sitl/run_px4_sih_profile.sh`
  - Updated the default SIH image tag and help text.
- `scripts/sitl/start_px4_sitl.sh`
  - Updated the manual helper default image and pull guidance.
- `.github/workflows/px4-sih-validation.yml`
  - Updated workflow default image without adding push or pull-request triggers.
- `tools/run_sitl_validation_suite.py`
  - Added bounded managed PX4 stdout capture, ANSI/prompt redraw scrubbing,
    manifest capture metadata, and post-close artifact status refresh.
- `tests/test_sitl_validation_contract.py`
  - Added SIH image/digest assertions and PX4 stdout scrubber regression
    coverage.
- `docs/drone-interface/04-infrastructure/README.md`
- `docs/drone-interface/04-infrastructure/sitl-setup.md`
- `tools/sitl_plans/README.md`
- `docs/reporting/agent-ops/codex-modernization/audits/2026-06-02-px4-sih-ci-validation-research.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-03-phase-3-px4-sih-ci-profile.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
  - Updated operational docs and report pointers so future agents do not copy
    the invalid tag or overclaim SIH runtime success.

## Evidence

Image pull/inspect:

```bash
sg docker -c 'docker pull px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01'
```

Result: pulled successfully with repo digest
`px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865`.

Guarded final probe:

```bash
sg docker -c 'PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
bash scripts/sitl/run_px4_sih_profile.sh \
  --mode execute-px4 \
  --px4-image px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01 \
  --px4-model sihsim_quadx \
  --artifact-root reports/sitl \
  --run-id 20260604T-pxe0039-official-sih-container-probe-reviewed \
  --startup-wait-s 20 \
  --timeout-s 5 \
  --json'
```

Result: incomplete, as expected for a PX4-only probe. Evidence directory:

```text
reports/sitl/20260604T-pxe0039-official-sih-container-probe-reviewed-phase2_follower_validation/
```

Key manifest evidence:

- `result`: `incomplete`
- `result_reason`: `One or more core runtime probes failed; inspect probe
  artifacts.`
- plan hash: `12504909390f49ac8b4102e96a24ab4065881485ce094b11fc9b7f4213d77051`
- `px4/container_metadata.json`: image/container ID match and expected repo
  digest check passed.
- `logs/px4_sitl.log`: 2,574 bytes,
  `sha256:3379ceb1236c87c5e1e88ae81447882fe0f778b331645c6149755a18c16009e1`.
- managed stdout capture: 162,054,071 raw bytes read, 16,205,148 prompt redraw
  lines filtered, 2,574 bytes written, not truncated, reader finished cleanly.
- `px4/params.txt`: collected from
  `/root/.local/share/px4/rootfs/parameters.bson`; manifest metadata marks
  `parameter_format=bson` and `readable_text_export=false`, so a text export
  is still preferred for reviewer-readable accepted evidence.
- `px4/ulog_manifest.json`: one ULog collected,
  `px4/ulog/000-container-07_15_37.ulg`, 4,133,504 bytes.
- `px4/tlog_manifest.json`: missing; no tlog was found in the SIH container.
- no leftover `pixeagle-px4-sitl-*` containers remained after the run.

Missing or incomplete evidence that correctly prevented a pass:

- `config/config.yaml`
- `route_map/mavlink_anywhere_endpoints.json`
- `route_map/mavlink_anywhere_profiles_summary.json`
- `route_map/mavlink_anywhere_config.json`
- `probes/pixeagle_status.json`
- `probes/pixeagle_current_config.json`
- `probes/pixeagle_follower_setpoints_status.json`
- `probes/mavlink2rest_mavlink.json`
- `scenarios/scenario_results.json`
- `logs/pixeagle.log`
- `px4/tlog_manifest.json`

Local MavlinkAnywhere note:

- The probe found something answering on `127.0.0.1:9070`.
- `/api/v1/status` and `/api/v1/diagnostics` returned 200.
- `/api/v1/endpoints` and `/api/v1/config` returned 500.
- `/api/v1/profiles/summary` returned 404.

This was not treated as a MavlinkAnywhere regression because the full routing
stack was not prepared for this PX4-only probe. It is recorded under PXE-0022
for the next sidecar/API compatibility slice, especially because local
MavlinkAnywhere remains behind `origin/main`.

Sidecar repo recheck:

```text
/home/alireza/mavlink-anywhere: local main at fd80c48/v3.0.8, origin/main at 7643d4d, latest tag v3.0.14
/home/alireza/smart-wifi-manager: local main at 25e0912/v2.1.11, origin/main at a5414fc, latest tag v2.1.14
/home/alireza/mavsdk_drone_show: local main at 2fae1e8a/v5.3.37-log-detail-sync-warning, origin/main at 6e6aec35, latest tag v5.5.52-simurgh-evidence-foundation
```

No sidecar checkout was pulled or changed in this slice.

## Independent Review

Three read-only reviewers checked the SIH/tag/log-capture slice before commit.
Findings were incorporated before this checkpoint was finalized:

- PX4/SIH evidence boundary reviewer:
  - flagged scenario wording that sounded like PX4-observed Offboard/cadence
    success while current executable checks mostly inspect PixEagle local state;
  - flagged target-loss/video-stall safe-publish wording that lacked
    PX4-observed publish/cadence assertions;
  - flagged binary `parameters.bson` copied to `px4/params.txt` as a
    readability risk.
- Docker/CI reviewer:
  - flagged that the infrastructure quick-start started
    `scripts/sitl/start_px4_sitl.sh` without first pulling the pinned image,
    while the helper uses Docker `--pull=never`;
  - flagged that workflow `px4_image` overrides cannot satisfy accepted
    evidence unless the plan digest is intentionally updated.
- Harness/log reviewer:
  - flagged that PX4 stdout capture could be marked collected if the reader
    thread failed or timed out;
  - flagged unbounded pending memory for a long unterminated stdout line;
  - flagged that the truncation marker was unlikely to appear when the byte cap
    was reached.

Corrections added before final validation:

- Plan scenario wording now distinguishes local PixEagle/OffboardCommander
  evidence from PX4-observed ULog/tlog/telemetry assertions tracked under
  PXE-0042.
- Managed PX4 stdout capture now reports `ok`, `thread_finished`,
  `reader_error`, bounded pending flushes, and truncation marker behavior; a
  capture failure marks the log artifact uncollected and keeps the run
  incomplete.
- Binary PX4 params discovery now records `parameter_format=bson` and
  `readable_text_export=false`.
- The infrastructure quick-start now pulls the pinned SIH image before using
  the `--pull=never` helper.
- The SIH workflow states that non-default image overrides are
  experimental/incomplete unless the plan digest is intentionally updated.

## Validation

Commands run:

```bash
python3 -m py_compile tools/run_sitl_validation_suite.py tests/test_sitl_validation_contract.py
```

Result: passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHONPATH=src pytest tests/test_sitl_validation_contract.py \
  tests/test_docs_infrastructure_consistency.py -q
```

Result: 61 passed.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHONPATH=src pytest tests/test_api_route_inventory.py \
  tests/unit/core_app/test_parameters_reload.py -q
```

Result: 14 passed.

```bash
PYTHON=/tmp/pixeagle-audit-venv/bin/python bash scripts/check_schema.sh
```

Result: schema is up-to-date.

```bash
PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
bash scripts/sitl/run_px4_sih_profile.sh --mode dry-run --json
```

Result: passed dry-run with plan hash
`12504909390f49ac8b4102e96a24ab4065881485ce094b11fc9b7f4213d77051`.

```bash
bash -n scripts/sitl/run_px4_sih_profile.sh scripts/sitl/start_px4_sitl.sh
git diff --check
```

Result: passed.

Runtime command:

```bash
sg docker -c 'PATH=/tmp/pixeagle-audit-venv/bin:$PATH \
PYTHON_BIN=/tmp/pixeagle-audit-venv/bin/python \
bash scripts/sitl/run_px4_sih_profile.sh --mode execute-px4 ... --json'
```

Result: exit code 3 with manifest result `incomplete`, which is the correct
fail-closed result for missing stack evidence.

## Risks And Open Questions

- This is not a PixEagle/PX4 behavior pass. PixEagle, MAVLink2REST, routing,
  scenario actions, tlog evidence, and parsed PX4 mode/cadence assertions were
  absent.
- SIH is useful L2 control-plane evidence only. It cannot validate tracker
  vision, camera latency, Gazebo visual geometry, HIL, field behavior, or
  real-aircraft safety.
- PX4 SIH stdout emits extreme prompt redraw traffic. The harness now filters
  and bounds this artifact, but ULog/tlog parsing must become the primary
  source for accepted Offboard mode and setpoint cadence evidence.
- A local MavlinkAnywhere service responded with partial/failed route APIs.
  Before accepted SITL evidence, rerun with a prepared current MavlinkAnywhere
  checkout and update PixEagle route/profile contracts if the API changed.
- `/home/alireza/mavsdk_drone_show` advanced to
  `v5.5.52-simurgh-evidence-foundation`; the Phase 4 API/MCP slice must
  re-review those newer standards before implementing PixEagle's typed
  `/api/v1`/MCP surface.

## Next Planned Slice

Proceed to the Phase 3/4 local evidence path:

1. Keep full official Gazebo L4 visual proof open for native Ubuntu GUI/GPU, a
   stronger headless runner, or a proven official-image startup workaround.
2. Use this official SIH layer for PX4 state-machine/control-plane evidence.
3. Implement PXE-0042 typed `/api/v1` SITL control actions and parsed PX4
   ULog/tlog or telemetry cadence assertions.
4. Add deterministic synthetic visual/tracker evidence on this VPS without
   claiming Gazebo visual SITL.
5. Reconcile the updated sidecar standards from `mavsdk_drone_show`,
   MavlinkAnywhere, and Smart Wi-Fi Manager before API/MCP changes.
